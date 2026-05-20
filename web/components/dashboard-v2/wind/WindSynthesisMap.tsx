'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import '@/styles/wind-synthesis.css';
import type { V2FlightPoint } from '../V2MissionMap';
import { isValidLngLat } from '../V2MissionMap';
import { snapPressureHpa } from '@/lib/wind/fetchWindGrid';
import type { StratolinkForecast } from '@/lib/wind/forecastTypes';
import { splitTrackSegments } from '@/lib/wind/trackSegments';
import WindForecastScrubber from './WindForecastScrubber';
import { useTickingNow } from '../shared';
import {
    buildForecastTimeline,
    positionAtTimelineMs,
    trackCoordsUpToMs,
} from '@/lib/wind/forecastTimeline';
import {
    formatGapAge,
    gpsGapHoursFromMs,
    STALE_GAP_REFRESH_MS,
    STALE_GPS_THRESHOLD_H,
} from '@/lib/wind/staleGpsExtrapolation';

export type WindSynthesisMapProps = {
    deviceId: string;
    callsign: string;
    observedTrack: V2FlightPoint[];
    /** Barometric altitude samples (incl. rows without GPS) for gap reconstruction. */
    baroSamples?: Array<{ time_utc: string; alt_m: number }>;
    startLat: number;
    startLon: number;
    launchLat?: number | null;
    launchLon?: number | null;
    pressureHpa: number;
    forecastHours?: number;
    anchorKey?: string;
    /** Wait until telemetry has loaded so we do not race an empty track vs full mission. */
    telemetryReady?: boolean;
    nullschoolUrl: string;
    lastAltM?: number | null;
};

/** One hue per semantic role — see renderer-legibility-fixes.md */
const COL = {
    observed: '#c9521f',
    reconstruction: '#3fb8a0',
    forecast: '#8e86e0',
    footprint: '#c08a4a',
    footprintEdge: '#d6a25c',
} as const;

type UncertaintyMode = 'ellipses' | 'spaghetti';

function fmtCoord(lat: number, lon: number): string {
    const ns = lat >= 0 ? 'N' : 'S';
    const ew = lon >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(2)}°${ns} ${Math.abs(lon).toFixed(2)}°${ew}`;
}

function fmtDuration(ms: number): string {
    const h = Math.floor(ms / 3_600_000);
    const m = Math.floor((ms % 3_600_000) / 60_000);
    return `${h}h ${String(m).padStart(2, '0')}m`;
}

/** Bias correction factors — avoid float artifacts like 1.0759999999999998 in UI. */
function fmtBiasSpeed(factor: number): string {
    return (Math.round(factor * 100) / 100).toFixed(2);
}

function fmtBiasDir(deg: number): string {
    const d = Math.round(deg);
    return d > 0 ? `+${d}` : `${d}`;
}

function lineGeoJson(coords: Array<[number, number]>) {
    if (coords.length < 2) return null;
    return {
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: coords },
        properties: {},
    };
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const r = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function obsTimeUtc(t: number): string {
    return new Date(t).toISOString();
}

function applyForecast(forecast: StratolinkForecast, setMc: (v: StratolinkForecast | null) => void) {
    setMc(forecast);
}

export default function WindSynthesisMap({
    deviceId,
    callsign,
    observedTrack,
    baroSamples,
    startLat,
    startLon,
    launchLat,
    launchLon,
    pressureHpa,
    forecastHours = 24,
    anchorKey = 'default',
    telemetryReady = true,
    nullschoolUrl,
    lastAltM = null,
}: WindSynthesisMapProps) {
    const mapRef = useRef<MapRef>(null);
    const didFitRef = useRef(false);
    const forecastOriginRef = useRef({ lat: startLat, lon: startLon });
    const levelHpa = snapPressureHpa(pressureHpa);
    const skipNextStaleAutoRef = useRef(true);
    /** Ignore out-of-order responses when anchorKey/effects fire overlapping loads. */
    const forecastReqRef = useRef(0);
    const anchorKeyRef = useRef(anchorKey);
    anchorKeyRef.current = anchorKey;
    /** Forecast displayed only when this matches anchorKey (avoids stale/wrong path flash). */
    const [loadedAnchorKey, setLoadedAnchorKey] = useState<string | null>(null);
    const propsRef = useRef({
        observedTrack,
        startLat,
        startLon,
        launchLat,
        launchLon,
        levelHpa,
        forecastHours,
        deviceId,
        callsign,
        lastAltM,
        baroSamples,
    });
    propsRef.current = {
        observedTrack,
        baroSamples,
        startLat,
        startLon,
        launchLat,
        launchLon,
        levelHpa,
        forecastHours,
        deviceId,
        callsign,
        lastAltM,
    };
    const [mapReady, setMapReady] = useState(false);
    const [mc, setMc] = useState<StratolinkForecast | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [uncertaintyMode, setUncertaintyMode] = useState<UncertaintyMode>('ellipses');
    const [scrubMs, setScrubMs] = useState<number | null>(null);
    /** User moved the slider — do not snap back to "now" when forecast/timeline refreshes. */
    const userPinnedScrubRef = useRef(false);
    const nowMs = useTickingNow(30_000);

    const lastGpsMs = observedTrack.length ? observedTrack[observedTrack.length - 1].t : 0;
    const liveGapH = gpsGapHoursFromMs(lastGpsMs, nowMs);
    const isStaleGps = liveGapH >= STALE_GPS_THRESHOLD_H;
    const staleRefreshKey = isStaleGps
        ? `${Math.floor(liveGapH)}h-${Math.floor(nowMs / STALE_GAP_REFRESH_MS)}`
        : 'fresh';

    const loadForecast = useCallback(async (opts?: { staleAuto?: boolean }) => {
        const p = propsRef.current;
        if (p.observedTrack.length < 1 || !isValidLngLat(p.startLat, p.startLon)) return;

        const reqId = ++forecastReqRef.current;
        const anchorAtStart = anchorKeyRef.current;
        forecastOriginRef.current = { lat: p.startLat, lon: p.startLon };
        if (!opts?.staleAuto) {
            setLoading(true);
            setMc(null);
            setLoadedAnchorKey(null);
        }
        setError(null);

        const applyIfCurrent = (forecast: StratolinkForecast) => {
            if (reqId !== forecastReqRef.current) return;
            if (anchorAtStart !== anchorKeyRef.current) return;
            applyForecast(forecast, setMc);
            setLoadedAnchorKey(anchorAtStart);
        };

        try {
            const first = p.observedTrack[0];
            const launch =
                p.launchLat != null && p.launchLon != null
                    ? { lat: p.launchLat, lon: p.launchLon, time_utc: obsTimeUtc(first.t) }
                    : { lat: first.lat, lon: first.lon, time_utc: obsTimeUtc(first.t) };

            const res = await fetch('/api/wind-forecast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                cache: 'no-store',
                body: JSON.stringify({
                    deviceId: p.deviceId,
                    mission: p.callsign,
                    launch,
                    observedTrack: p.observedTrack.map((pt) => ({
                        lat: pt.lat,
                        lon: pt.lon,
                        t: obsTimeUtc(pt.t),
                        alt_m: p.lastAltM,
                    })),
                    baroSamples: p.baroSamples,
                    pressureHpa: p.levelHpa,
                    forecastHours: p.forecastHours,
                }),
            });
            const data = await res.json();
            if (reqId !== forecastReqRef.current) return;
            if (!res.ok) throw new Error(data.error ?? 'Forecast failed');
            applyIfCurrent(data as StratolinkForecast);
        } catch (e) {
            if (reqId !== forecastReqRef.current) return;
            setError(e instanceof Error ? e.message : 'Forecast failed');
            setMc(null);
        } finally {
            if (reqId === forecastReqRef.current) setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!telemetryReady) return;
        skipNextStaleAutoRef.current = true;
        userPinnedScrubRef.current = false;
        setScrubMs(null);
        loadForecast();
        didFitRef.current = false;
    }, [anchorKey, telemetryReady, loadForecast]);

    /** Recompute stale back-drift + forward forecast as the GPS gap grows (hourly + every 15 min). */
    useEffect(() => {
        if (!isStaleGps) {
            skipNextStaleAutoRef.current = true;
            return;
        }
        if (skipNextStaleAutoRef.current) {
            skipNextStaleAutoRef.current = false;
            return;
        }
        loadForecast({ staleAuto: true });
    }, [staleRefreshKey, isStaleGps, loadForecast]);

    const segments = useMemo(() => splitTrackSegments(observedTrack), [observedTrack]);
    const showEllipses = uncertaintyMode === 'ellipses';
    const ensembleOpacity = uncertaintyMode === 'ellipses' ? 0.04 : 0.1;

    const forecastReady = loadedAnchorKey === anchorKey && mc != null;
    const showUpdating = loading && forecastReady;

    const nominalPath = forecastReady ? (mc?.nominal_path ?? []) : [];
    /** Hours actually in the loaded forecast (path is one point per hour from origin). */
    const effectiveHorizonH =
        mc?.forecast_horizon_h ??
        (nominalPath.length > 1 ? nominalPath.length - 1 : forecastHours);

    const ellipses90GeoJson = useMemo(() => {
        if (!forecastReady || !mc || !showEllipses) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ellipses.map((e) => ({
                type: 'Feature' as const,
                properties: { t_hours: e.t_hours },
                geometry: { type: 'Polygon' as const, coordinates: [e.e90.polygon] },
            })),
        };
    }, [forecastReady, mc, showEllipses]);

    const ellipses50GeoJson = useMemo(() => {
        if (!forecastReady || !mc || !showEllipses) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ellipses.map((e) => ({
                type: 'Feature' as const,
                properties: { t_hours: e.t_hours },
                geometry: { type: 'Polygon' as const, coordinates: [e.e50.polygon] },
            })),
        };
    }, [forecastReady, mc, showEllipses]);

    const ensembleGeoJson = useMemo(() => {
        if (!forecastReady || !mc) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ensemble.map((traj) => ({
                type: 'Feature' as const,
                properties: {},
                geometry: { type: 'LineString' as const, coordinates: traj },
            })),
        };
    }, [forecastReady, mc]);

    const hourLabels = useMemo(() => {
        if (!forecastReady || !nominalPath.length) return { type: 'FeatureCollection' as const, features: [] };
        const pathHours = nominalPath.length - 1;
        const labelHours = new Set(
            [6, 12, 18, 24].filter((h) => h <= effectiveHorizonH && h <= pathHours),
        );
        const features = nominalPath.slice(1).map((p, i) => {
            const hour = i + 1;
            return {
                type: 'Feature' as const,
                properties: { label: labelHours.has(hour) ? `+${hour}h` : '' },
                geometry: { type: 'Point' as const, coordinates: p },
            };
        });
        return { type: 'FeatureCollection' as const, features };
    }, [nominalPath, effectiveHorizonH]);

    const firstObs = observedTrack[0];
    const lastObs = observedTrack.length ? observedTrack[observedTrack.length - 1] : null;
    const endPoint = forecastReady ? (mc?.endpoint ?? null) : null;
    const e90_at_horizon =
        mc?.ellipses.find((e) => e.t_hours === effectiveHorizonH)?.e90 ??
        mc?.ellipses[mc.ellipses.length - 1]?.e90;

    const launch = useMemo(() => {
        if (launchLat != null && launchLon != null) return { lat: launchLat, lon: launchLon };
        if (firstObs) return { lat: firstObs.lat, lon: firstObs.lon };
        return null;
    }, [launchLat, launchLon, firstObs]);

    const observedRange = useMemo(() => {
        if (!firstObs || !lastObs) return null;
        return {
            start: new Date(firstObs.t),
            end: new Date(lastObs.t),
            duration: new Date(lastObs.t).getTime() - new Date(firstObs.t).getTime(),
        };
    }, [firstObs, lastObs]);

    const predDistanceKm = useMemo(() => {
        if (!lastObs || !endPoint) return null;
        return haversineKm(lastObs.lat, lastObs.lon, endPoint.lat, endPoint.lon);
    }, [lastObs, endPoint]);

    const obsCoords = useMemo(
        () => segments.observed.map((p) => [p.lon, p.lat] as [number, number]),
        [segments.observed],
    );

    const resumedCoords = segments.resumed.map((p) => [p.lon, p.lat] as [number, number]);

    const reconstructedPath = forecastReady ? (mc?.observed.reconstructed_path ?? []) : [];
    const gpsFixes = forecastReady ? (mc?.observed.gps_fixes ?? []) : [];
    const reconstructedTrack = useMemo(() => {
        const raw = forecastReady ? mc?.observed.reconstructed_track : undefined;
        if (raw?.length) {
            return raw.map((p) => ({
                lat: p.lat,
                lon: p.lon,
                t: new Date(p.time_utc).getTime(),
            }));
        }
        if (
            reconstructedPath.length >= 2 &&
            gpsFixes.length >= 2 &&
            forecastReady
        ) {
            const t0 = new Date(gpsFixes[0].time_utc).getTime();
            const t1 = new Date(gpsFixes[gpsFixes.length - 1].time_utc).getTime();
            const span = t1 - t0 || 1;
            return reconstructedPath.map(([lon, lat], i) => ({
                lon,
                lat,
                t: t0 + (i / (reconstructedPath.length - 1)) * span,
            }));
        }
        return [];
    }, [
        forecastReady,
        mc?.observed.reconstructed_track,
        reconstructedPath,
        gpsFixes,
    ]);

    const gapBridges = forecastReady ? (mc?.observed.gap_bridges ?? []) : [];
    const reconstructionGaps = forecastReady ? (mc?.observed.reconstruction_gaps ?? []) : [];
    const corridorOccupancyGaps = reconstructionGaps.filter(
        (g) => g.mode === 'corridor' && g.occupancy && g.occupancy.cells.length > 0,
    );
    const nontrivialGaps = reconstructionGaps.filter((g) => !g.short);
    const corridorGaps = nontrivialGaps.filter((g) => g.mode === 'corridor');
    const nonShortGaps = nontrivialGaps;

    const driftCoords = useMemo(() => {
        if (!forecastReady) return [];
        if (mc?.stale_gps && mc.observed.drift_segment?.length) return mc.observed.drift_segment;
        return [];
    }, [forecastReady, mc?.stale_gps, mc?.observed.drift_segment]);

    const impliedNowCoord = useMemo((): [number, number] | null => {
        if (!forecastReady || !mc?.stale_gps) return null;
        if (nominalPath.length > 0) return nominalPath[0];
        if (driftCoords.length > 0) return driftCoords[driftCoords.length - 1];
        return null;
    }, [forecastReady, mc?.stale_gps, nominalPath, driftCoords]);

    const predCoords = nominalPath;

    const timeline = useMemo(() => {
        if (!forecastReady || !mc || !lastObs) return null;
        const tNow = new Date(mc.forecast_origin.time_utc).getTime();
        return buildForecastTimeline(
            observedTrack,
            tNow,
            effectiveHorizonH,
            lastObs.t,
            Boolean(mc.stale_gps),
        );
    }, [forecastReady, mc, lastObs, observedTrack, effectiveHorizonH]);

    const hadTimelineRef = useRef(false);
    useEffect(() => {
        if (!timeline) {
            hadTimelineRef.current = false;
            return;
        }
        if (!hadTimelineRef.current) {
            hadTimelineRef.current = true;
            if (!userPinnedScrubRef.current) {
                setScrubMs(timeline.tNow);
            }
        }
    }, [timeline]);

    const handleScrubMs = useCallback(
        (t: number) => {
            const tNow = timeline?.tNow;
            userPinnedScrubRef.current =
                tNow == null || Math.abs(t - tNow) >= 60_000;
            setScrubMs(t);
        },
        [timeline?.tNow],
    );

    const effectiveScrubMs = scrubMs ?? timeline?.tNow ?? 0;

    const scrubPosition = useMemo(() => {
        if (!timeline || !forecastReady) return null;
        return positionAtTimelineMs(
            effectiveScrubMs,
            observedTrack,
            driftCoords,
            nominalPath,
            timeline,
            reconstructedTrack.length >= 2 ? reconstructedTrack : undefined,
        );
    }, [
        timeline,
        forecastReady,
        effectiveScrubMs,
        observedTrack,
        driftCoords,
        nominalPath,
        reconstructedTrack,
    ]);

    const scrubAtNow = timeline != null && Math.abs(effectiveScrubMs - timeline.tNow) < 60_000;

    const scrubGapInfo = useMemo(() => {
        if (
            !forecastReady ||
            !reconstructionGaps.length ||
            (scrubPosition?.segment !== 'reconstructed' && scrubPosition?.segment !== 'observed')
        ) {
            return null;
        }
        for (let i = 0; i < gpsFixes.length - 1; i++) {
            const t0 = new Date(gpsFixes[i].time_utc).getTime();
            const t1 = new Date(gpsFixes[i + 1].time_utc).getTime();
            if (effectiveScrubMs >= t0 && effectiveScrubMs <= t1) {
                const g = reconstructionGaps.find((x) => x.from_idx === i && x.to_idx === i + 1);
                if (!g || g.short) return null;
                return g;
            }
        }
        return null;
    }, [forecastReady, scrubPosition, reconstructionGaps, gpsFixes, effectiveScrubMs]);

    const reconstructedFullLine = useMemo(
        () => lineGeoJson(reconstructedPath.length >= 2 ? reconstructedPath : []),
        [reconstructedPath],
    );

    const reconstructedScrubbedLine = useMemo(() => {
        if (reconstructedTrack.length < 2 || !timeline) return null;
        const tEnd = Math.min(effectiveScrubMs, timeline.tLastFix);
        return lineGeoJson(trackCoordsUpToMs(reconstructedTrack, tEnd));
    }, [reconstructedTrack, effectiveScrubMs, timeline]);

    const gapBridgesGeoJson = useMemo(() => {
        if (!gapBridges.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: gapBridges.map((path, i) => ({
                type: 'Feature' as const,
                properties: { gap: i, mode: nonShortGaps[i]?.mode ?? 'line' },
                geometry: { type: 'LineString' as const, coordinates: path },
            })),
        };
    }, [gapBridges, nonShortGaps]);

    const gapOccupancyGeoJson = useMemo(() => {
        const features: Array<{
            type: 'Feature';
            properties: { gap: number; d: number };
            geometry: { type: 'Polygon'; coordinates: Array<Array<[number, number]>> };
        }> = [];
        reconstructionGaps.forEach((g, gi) => {
            if (g.mode !== 'corridor' || !g.occupancy?.cells.length) return;
            const o = g.occupancy;
            for (const c of o.cells) {
                const lon0 = o.lon0 + c.j * o.dLon;
                const lat0 = o.lat0 + c.i * o.dLat;
                const lon1 = lon0 + o.dLon;
                const lat1 = lat0 + o.dLat;
                features.push({
                    type: 'Feature',
                    properties: { gap: gi, d: c.d },
                    geometry: {
                        type: 'Polygon',
                        coordinates: [
                            [
                                [lon0, lat0],
                                [lon1, lat0],
                                [lon1, lat1],
                                [lon0, lat1],
                                [lon0, lat0],
                            ],
                        ],
                    },
                });
            }
        });
        if (!features.length) return null;
        return { type: 'FeatureCollection' as const, features };
    }, [reconstructionGaps]);

    const reconGapEllipsesGeoJson = useMemo(() => {
        const e90: Array<{
            type: 'Feature';
            properties: { gap: number; frac: number };
            geometry: { type: 'Polygon'; coordinates: Array<Array<[number, number]>> };
        }> = [];
        const e50: typeof e90 = [];
        reconstructionGaps.forEach((g, gi) => {
            if (g.mode === 'corridor' || !g.ellipses?.length) return;
            for (const e of g.ellipses) {
                e90.push({
                    type: 'Feature',
                    properties: { gap: gi, frac: e.frac },
                    geometry: { type: 'Polygon', coordinates: [e.e90.polygon] },
                });
                e50.push({
                    type: 'Feature',
                    properties: { gap: gi, frac: e.frac },
                    geometry: { type: 'Polygon', coordinates: [e.e50.polygon] },
                });
            }
        });
        if (!e90.length) return null;
        return {
            e90: { type: 'FeatureCollection' as const, features: e90 },
            e50: { type: 'FeatureCollection' as const, features: e50 },
        };
    }, [reconstructionGaps]);

    const freezeLine = useMemo(() => lineGeoJson(driftCoords), [driftCoords]);
    const observedLine = useMemo(() => lineGeoJson(obsCoords), [obsCoords]);
    const resumedLine = useMemo(() => lineGeoJson(resumedCoords), [resumedCoords]);
    const predictedLine = useMemo(() => lineGeoJson(predCoords), [predCoords]);

    const allPoints = useMemo(() => {
        const pts = [
            ...observedTrack,
            ...nominalPath.map(([lon, lat]) => ({ lat, lon, t: '' })),
        ];
        for (const [lon, lat] of reconstructedPath) pts.push({ lat, lon, t: '' });
        for (const path of gapBridges) {
            for (const [lon, lat] of path) pts.push({ lat, lon, t: '' });
        }
        if (e90_at_horizon?.polygon) {
            for (const [lon, lat] of e90_at_horizon.polygon) pts.push({ lat, lon, t: '' });
        }
        return pts.filter((p) => isValidLngLat(p.lat, p.lon));
    }, [observedTrack, nominalPath, reconstructedPath, gapBridges, e90_at_horizon]);

    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || didFitRef.current) return;
        if (!forecastReady) {
            const obsOnly = observedTrack.filter((p) => isValidLngLat(p.lat, p.lon));
            if (obsOnly.length === 0) return;
            const lons = obsOnly.map((p) => p.lon);
            const lats = obsOnly.map((p) => p.lat);
            map.fitBounds(
                [
                    [Math.min(...lons) - 0.8, Math.min(...lats) - 0.6],
                    [Math.max(...lons) + 0.8, Math.max(...lats) + 0.5],
                ],
                { padding: { top: 70, bottom: 40, left: 280, right: 120 }, duration: 0 },
            );
            return;
        }
        if (allPoints.length === 0) return;
        const lons = allPoints.map((p) => p.lon);
        const lats = allPoints.map((p) => p.lat);
        map.fitBounds(
            [
                [Math.min(...lons) - 0.8, Math.min(...lats) - 0.6],
                [Math.max(...lons) + 0.8, Math.max(...lats) + 0.5],
            ],
            { padding: { top: 70, bottom: 40, left: 280, right: 120 }, duration: didFitRef.current ? 900 : 0 },
        );
        didFitRef.current = true;
    }, [allPoints, forecastReady, observedTrack]);

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
        return <div style={{ padding: 24, color: 'var(--sl-text-dim)' }}>Mapbox token required</div>;
    }

    return (
        <div className="wind-synthesis-root">
            <div className="wind-synthesis-topbar">
                <div className="wind-synthesis-brand">
                    <div className="wind-synthesis-eyebrow">
                        Stratolink · Monte Carlo · GFS {mc?.level_hpa ?? levelHpa} hPa
                        {mc ? ` · ${mc.metadata.n_ensemble} members` : ''}
                    </div>
                    <div className="wind-synthesis-title">{callsign}</div>
                </div>
                <div className="wind-synthesis-divider" />
                <div className="wind-synthesis-meta">
                    {observedRange && (
                        <div>
                            <b>Observed</b>{' '}
                            {observedRange.start.toLocaleString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                                timeZone: 'UTC',
                            })}{' '}
                            UTC →{' '}
                            {observedRange.end.toLocaleString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit',
                                timeZone: 'UTC',
                            })}{' '}
                            UTC
                        </div>
                    )}
                    {loading && !forecastReady && (
                        <div style={{ color: 'rgba(230,208,136,.75)' }}>
                            <b>Forecast</b> computing…
                        </div>
                    )}
                    {showUpdating && (
                        <div style={{ color: 'rgba(200,212,232,.45)' }}>
                            <b>Forecast</b> updating…
                        </div>
                    )}
                    {forecastReady && nontrivialGaps.length > 0 && (
                        <div style={{ color: 'rgba(63,184,160,.9)' }}>
                            <b>Reconstructed</b> {nontrivialGaps.length} GPS gap
                            {nontrivialGaps.length === 1 ? '' : 's'}
                            {corridorGaps.length > 0
                                ? ` · ${corridorGaps.length} under-determined (occupancy footprint)`
                                : ''}{' '}
                            (hourly GFS + particle smoother)
                        </div>
                    )}
                    {endPoint && forecastReady && !showUpdating && (
                        <div>
                            <b>Forecast</b>{' '}
                            {mc?.stale_gps ? (
                                <>
                                    +{effectiveHorizonH}h from implied now ({formatGapAge(liveGapH)} since
                                    last GPS) · endpoint{' '}
                                </>
                            ) : (
                                <>+{effectiveHorizonH}h from last fix · endpoint </>
                            )}
                            {endPoint.lat.toFixed(2)}°N {Math.abs(endPoint.lon).toFixed(2)}°W
                        </div>
                    )}
                </div>
                <div className="wind-synthesis-spacer" />
                <div className="wind-synthesis-mode-toggle">
                    <button
                        type="button"
                        className={`wind-synthesis-mode-btn${uncertaintyMode === 'ellipses' ? ' active' : ''}`}
                        onClick={() => setUncertaintyMode('ellipses')}
                    >
                        Ellipses
                    </button>
                    <button
                        type="button"
                        className={`wind-synthesis-mode-btn${uncertaintyMode === 'spaghetti' ? ' active' : ''}`}
                        onClick={() => setUncertaintyMode('spaghetti')}
                    >
                        Spaghetti
                    </button>
                </div>
                <a
                    href={nullschoolUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="wind-synthesis-ns-link"
                >
                    nullschool ↗
                </a>
                <button
                    type="button"
                    className="wind-synthesis-mode-btn"
                    style={{ marginLeft: 4 }}
                    disabled={loading}
                    onClick={() => {
                        didFitRef.current = false;
                        loadForecast();
                    }}
                >
                    {loading ? '…' : 'Refresh'}
                </button>
            </div>

            <div className="wind-synthesis-alerts">
            {forecastReady && mc?.stale_gps && (
                <div className="wind-synthesis-bias-banner wind-synthesis-stale-banner">
                    <div className="wind-synthesis-bias-label">Stale GPS · implied drift to now</div>
                    <div className="wind-synthesis-bias-body">
                        Last fix{' '}
                        {new Date(mc.stale_gps.last_fix_time_utc).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                            timeZone: 'UTC',
                        })}{' '}
                        UTC · <b>{formatGapAge(liveGapH)}</b> back-drift (hourly GFS, auto-updates
                        every 15m) · forward forecast uses current winds
                    </div>
                </div>
            )}

            {forecastReady && mc && mc.bias_correction.n_samples > 0 && (
                <div className="wind-synthesis-bias-banner wind-synthesis-calibration-banner">
                    <div className="wind-synthesis-bias-label">Forecast calibrated with in-flight data</div>
                    <div className="wind-synthesis-bias-body">
                        Observed drift vs GFS: speed ×<b>{fmtBiasSpeed(mc.bias_correction.speed_factor)}</b>, direction{' '}
                        <b>{fmtBiasDir(mc.bias_correction.direction_offset_deg)}°</b>
                        {mc.bias_correction.capped ? ' (capped)' : ''}. Applied to the forward path.
                    </div>
                </div>
            )}

            {error && <div className="wind-synthesis-alert-error">{error}</div>}
            </div>

            <div className="wind-synthesis-map">
                {!error && !forecastReady && (
                    <div className="wind-synthesis-forecast-loading" aria-live="polite">
                        {!telemetryReady
                            ? 'Loading flight data…'
                            : 'Computing Monte Carlo forecast…'}
                    </div>
                )}
                <Map
                    ref={mapRef}
                    mapboxAccessToken={token}
                    initialViewState={{ longitude: -106, latitude: 37.5, zoom: 4.05 }}
                    style={{ width: '100%', height: '100%' }}
                    mapStyle="mapbox://styles/mapbox/dark-v11"
                    attributionControl={false}
                    onLoad={() => setMapReady(true)}
                >
                    {ellipses90GeoJson && showEllipses && (
                        <Source id="ws-e90" type="geojson" data={ellipses90GeoJson}>
                            <Layer
                                id="ws-e90-stroke"
                                type="line"
                                paint={{
                                    'line-color': COL.forecast,
                                    'line-width': 1,
                                    'line-opacity': 0.45,
                                    'line-dasharray': [3, 4],
                                }}
                            />
                        </Source>
                    )}

                    {ellipses50GeoJson && showEllipses && (
                        <Source id="ws-e50" type="geojson" data={ellipses50GeoJson}>
                            <Layer
                                id="ws-e50-fill"
                                type="fill"
                                paint={{ 'fill-color': COL.forecast, 'fill-opacity': 0.12 }}
                            />
                            <Layer
                                id="ws-e50-stroke"
                                type="line"
                                paint={{
                                    'line-color': COL.forecast,
                                    'line-width': 1.1,
                                    'line-opacity': 0.55,
                                }}
                            />
                        </Source>
                    )}

                    {ensembleGeoJson && (
                        <Source id="ws-ensemble" type="geojson" data={ensembleGeoJson}>
                            <Layer
                                id="ws-ensemble-lines"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.forecast,
                                    'line-width': 1,
                                    'line-opacity': ensembleOpacity,
                                }}
                            />
                        </Source>
                    )}

                    {reconstructedFullLine && (
                        <Source id="ws-reconstructed-full" type="geojson" data={reconstructedFullLine}>
                            <Layer
                                id="ws-reconstructed-full-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.reconstruction,
                                    'line-width': 2,
                                    'line-dasharray': [2, 2],
                                    'line-opacity': 0.45,
                                }}
                            />
                        </Source>
                    )}

                    {reconstructedScrubbedLine && (
                        <Source id="ws-reconstructed-scrub" type="geojson" data={reconstructedScrubbedLine}>
                            <Layer
                                id="ws-reconstructed-scrub-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.reconstruction,
                                    'line-width': 3,
                                    'line-opacity': 0.95,
                                }}
                            />
                        </Source>
                    )}

                    {reconGapEllipsesGeoJson && showEllipses && (
                        <>
                            <Source id="ws-recon-gap-e90" type="geojson" data={reconGapEllipsesGeoJson.e90}>
                                <Layer
                                    id="ws-recon-gap-e90-stroke"
                                    type="line"
                                    paint={{
                                        'line-color': COL.reconstruction,
                                        'line-width': 1,
                                        'line-opacity': 0.45,
                                        'line-dasharray': [3, 4],
                                    }}
                                />
                            </Source>
                            <Source id="ws-recon-gap-e50" type="geojson" data={reconGapEllipsesGeoJson.e50}>
                                <Layer
                                    id="ws-recon-gap-e50-fill"
                                    type="fill"
                                    paint={{
                                        'fill-color': COL.reconstruction,
                                        'fill-opacity': 0.12,
                                    }}
                                />
                                <Layer
                                    id="ws-recon-gap-e50-stroke"
                                    type="line"
                                    paint={{
                                        'line-color': COL.reconstruction,
                                        'line-width': 1.1,
                                        'line-opacity': 0.55,
                                    }}
                                />
                            </Source>
                        </>
                    )}

                    {gapOccupancyGeoJson && (
                        <Source id="ws-occupancy" type="geojson" data={gapOccupancyGeoJson}>
                            <Layer
                                id="ws-occupancy-fill"
                                type="fill"
                                paint={{
                                    'fill-color': COL.footprint,
                                    'fill-antialias': false,
                                    'fill-opacity': [
                                        'interpolate',
                                        ['linear'],
                                        ['get', 'd'],
                                        0,
                                        0.14,
                                        0.5,
                                        0.36,
                                        1,
                                        0.6,
                                    ],
                                }}
                            />
                            <Layer
                                id="ws-occupancy-edge"
                                type="line"
                                paint={{
                                    'line-color': COL.footprintEdge,
                                    'line-width': 0.5,
                                    'line-opacity': 0.28,
                                }}
                            />
                        </Source>
                    )}

                    {gapBridgesGeoJson && (
                        <Source id="ws-reconstructed" type="geojson" data={gapBridgesGeoJson}>
                            <Layer
                                id="ws-reconstructed-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': [
                                        'match',
                                        ['get', 'mode'],
                                        'corridor',
                                        COL.footprint,
                                        COL.reconstruction,
                                    ],
                                    'line-width': 2.5,
                                    'line-dasharray': [3, 3],
                                    'line-opacity': [
                                        'match',
                                        ['get', 'mode'],
                                        'corridor',
                                        0.45,
                                        0.92,
                                    ],
                                }}
                            />
                        </Source>
                    )}

                    {freezeLine && (
                        <Source id="ws-freeze" type="geojson" data={freezeLine}>
                            <Layer
                                id="ws-freeze-line"
                                type="line"
                                paint={{
                                    'line-color': 'rgba(160, 175, 195, 0.9)',
                                    'line-width': 2.5,
                                    'line-dasharray': [4, 4],
                                    'line-opacity': 0.85,
                                }}
                            />
                        </Source>
                    )}

                    {observedLine && (
                        <Source id="ws-observed" type="geojson" data={observedLine}>
                            <Layer
                                id="ws-observed-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.observed,
                                    'line-width': 2.5,
                                    'line-opacity': 0.92,
                                }}
                            />
                        </Source>
                    )}

                    {resumedLine && (
                        <Source id="ws-resumed" type="geojson" data={resumedLine}>
                            <Layer
                                id="ws-resumed-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.observed,
                                    'line-width': 2,
                                    'line-opacity': 0.75,
                                    'line-dasharray': [4, 3],
                                }}
                            />
                        </Source>
                    )}

                    {predictedLine && (
                        <Source id="ws-predicted" type="geojson" data={predictedLine}>
                            <Layer
                                id="ws-predicted-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': COL.forecast,
                                    'line-width': 2.2,
                                    'line-opacity': 0.92,
                                    'line-dasharray': [5, 4],
                                }}
                            />
                        </Source>
                    )}

                    {hourLabels.features.length > 0 && (
                        <Source id="ws-hours" type="geojson" data={hourLabels}>
                            <Layer
                                id="ws-hour-dots"
                                type="circle"
                                paint={{
                                    'circle-radius': 3.2,
                                    'circle-color': COL.forecast,
                                    'circle-stroke-color': 'rgba(8,13,23,.75)',
                                    'circle-stroke-width': 1.5,
                                }}
                            />
                            <Layer
                                id="ws-hour-text"
                                type="symbol"
                                layout={{
                                    'text-field': ['get', 'label'],
                                    'text-size': 9.5,
                                    'text-offset': [0, -1.5],
                                    'text-anchor': 'bottom',
                                }}
                                paint={{
                                    'text-color': 'rgba(180,170,230,.85)',
                                    'text-halo-color': 'rgba(8,13,23,.6)',
                                    'text-halo-width': 1.2,
                                }}
                            />
                        </Source>
                    )}

                    {launch && (
                        <Marker longitude={launch.lon} latitude={launch.lat} anchor="center">
                            <div
                                className="wind-synthesis-waypoint"
                                style={{ width: 12, height: 12, background: '#2d8c55' }}
                                title="Launch"
                            />
                        </Marker>
                    )}

                    {lastObs && (
                        <Marker longitude={lastObs.lon} latitude={lastObs.lat} anchor="center">
                            <div
                                className="wind-synthesis-waypoint"
                                style={{ width: 11, height: 11, background: COL.observed }}
                                title={mc?.stale_gps ? 'Last GPS fix (stale)' : 'Last fix'}
                            />
                        </Marker>
                    )}

                    {scrubAtNow && mc?.stale_gps && impliedNowCoord && (
                        <Marker
                            longitude={impliedNowCoord[0]}
                            latitude={impliedNowCoord[1]}
                            anchor="center"
                        >
                            <div
                                className="wind-synthesis-waypoint"
                                style={{
                                    width: 13,
                                    height: 13,
                                    background: COL.forecast,
                                    boxShadow: '0 0 0 2px rgba(8,13,23,.85)',
                                }}
                                title="Implied position now · forecast start"
                            />
                        </Marker>
                    )}

                    {forecastReady && endPoint && (
                        <Marker longitude={endPoint.lon} latitude={endPoint.lat} anchor="center">
                            <div
                                className="wind-synthesis-waypoint"
                                style={{
                                    width: 14,
                                    height: 14,
                                    background: COL.forecast,
                                    border: '2.5px solid rgba(255,255,255,.85)',
                                    boxShadow: '0 1px 7px rgba(0,0,0,.5)',
                                }}
                                title={
                                    e90_at_horizon
                                        ? `+${effectiveHorizonH}h forecast · ${fmtCoord(endPoint.lat, endPoint.lon)} · 90% ±${Math.round(e90_at_horizon.semi_a_km)}×${Math.round(e90_at_horizon.semi_b_km)} km`
                                        : `+${effectiveHorizonH}h forecast · ${fmtCoord(endPoint.lat, endPoint.lon)}`
                                }
                            />
                        </Marker>
                    )}

                    {scrubPosition && (
                        <Marker
                            longitude={scrubPosition.lon}
                            latitude={scrubPosition.lat}
                            anchor="center"
                        >
                            <div
                                className={`wind-synthesis-scrub-marker wind-synthesis-scrub-marker--${scrubPosition.segment}`}
                                title="Scrubbed position"
                            />
                        </Marker>
                    )}

                </Map>

            </div>

            <div className="wind-synthesis-info">
                <div className="wind-synthesis-ip-section">
                    <div className="wind-synthesis-ip-header">Observed flight</div>
                    {launch && (
                        <div className="wind-synthesis-ip-row">
                            <span className="wind-synthesis-ip-key">Launch</span>
                            <span className="wind-synthesis-ip-val">{fmtCoord(launch.lat, launch.lon)}</span>
                        </div>
                    )}
                    {lastObs && (
                        <div className="wind-synthesis-ip-row">
                            <span className="wind-synthesis-ip-key">Last GPS fix</span>
                            <span className="wind-synthesis-ip-val">{fmtCoord(lastObs.lat, lastObs.lon)}</span>
                        </div>
                    )}
                    <div className="wind-synthesis-ip-row">
                        <span className="wind-synthesis-ip-key">Float level</span>
                        <span className="wind-synthesis-ip-val">
                            {lastAltM != null ? `~${Math.round(lastAltM).toLocaleString()} m · ` : ''}
                            {levelHpa} hPa
                        </span>
                    </div>
                    {observedRange && (
                        <div className="wind-synthesis-ip-row">
                            <span className="wind-synthesis-ip-key">Duration tracked</span>
                            <span className="wind-synthesis-ip-val">{fmtDuration(observedRange.duration)}</span>
                        </div>
                    )}
                </div>
                <div className="wind-synthesis-ip-section">
                    <div className="wind-synthesis-ip-header">GFS +{effectiveHorizonH}h prediction</div>
                    {loading && !forecastReady && (
                        <div className="wind-synthesis-ip-row">
                            <span className="wind-synthesis-ip-key">Status</span>
                            <span className="wind-synthesis-ip-val">Computing…</span>
                        </div>
                    )}
                    {forecastReady && endPoint && (
                        <>
                            <div className="wind-synthesis-ip-row">
                                <span className="wind-synthesis-ip-key">Predicted position</span>
                                <span className="wind-synthesis-ip-val wind-synthesis-ip-accent">
                                    {fmtCoord(endPoint.lat, endPoint.lon)}
                                </span>
                            </div>
                            {endPoint.wind && (
                                <div className="wind-synthesis-ip-row">
                                    <span className="wind-synthesis-ip-key">Wind at endpoint</span>
                                    <span className="wind-synthesis-ip-val">
                                        {endPoint.wind.speed_mps} m/s · {endPoint.wind.dir_deg}°
                                    </span>
                                </div>
                            )}
                            {e90_at_horizon && (
                                <div className="wind-synthesis-ip-row">
                                    <span className="wind-synthesis-ip-key">90% spread (+{effectiveHorizonH}h)</span>
                                    <span className="wind-synthesis-ip-val">
                                        ±{Math.round(e90_at_horizon.semi_a_km)} × {Math.round(e90_at_horizon.semi_b_km)} km
                                    </span>
                                </div>
                            )}
                            {predDistanceKm != null && (
                                <div className="wind-synthesis-ip-row">
                                    <span className="wind-synthesis-ip-key">Est. distance</span>
                                    <span className="wind-synthesis-ip-val">~{Math.round(predDistanceKm).toLocaleString()} km</span>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>

            <div className="wind-synthesis-legend">
                <div className="wind-synthesis-lg-title">Map Key</div>

                <div className="wind-synthesis-lg-group">Observed</div>
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, height: 2.5, borderRadius: 2, background: COL.observed }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>GPS track</span>
                </div>

                <div className="wind-synthesis-lg-group">Reconstructed</div>
                {reconstructedPath.length > 1 && (
                    <div className="wind-synthesis-lg-row">
                        <div style={{ width: 26, borderTop: `2px dashed ${COL.reconstruction}88` }} />
                        <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Full path (faint)</span>
                    </div>
                )}
                {reconstructedTrack.length > 1 && (
                    <div className="wind-synthesis-lg-row">
                        <div style={{ width: 26, height: 2.5, borderRadius: 2, background: COL.reconstruction }} />
                        <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Path to scrub time</span>
                    </div>
                )}
                {corridorOccupancyGaps.length > 0 && (
                    <div className="wind-synthesis-lg-row">
                        <div
                            style={{
                                width: 26,
                                height: 10,
                                borderRadius: 2,
                                background: `linear-gradient(90deg, ${COL.footprint}22, ${COL.footprint}99)`,
                            }}
                        />
                        <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Occupancy footprint</span>
                    </div>
                )}

                <div className="wind-synthesis-lg-group">Forecast</div>
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, borderTop: `2px dashed ${COL.forecast}cc` }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Nominal path</span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div
                        style={{
                            width: 26,
                            height: 10,
                            borderRadius: 2,
                            background: `${COL.forecast}33`,
                            border: `1px solid ${COL.forecast}99`,
                        }}
                    />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>50% / 90% ellipses</span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, borderTop: `1px solid ${COL.forecast}55` }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>
                        {mc?.metadata.n_ensemble ?? 200} ensemble members
                    </span>
                </div>
            </div>


            {forecastReady && timeline && scrubPosition && (
                <WindForecastScrubber
                    timeline={timeline}
                    scrubMs={effectiveScrubMs}
                    onScrubMs={handleScrubMs}
                    position={scrubPosition}
                    observedTrack={observedTrack}
                    forecastHorizonH={effectiveHorizonH}
                    reconstructionGap={scrubGapInfo}
                />
            )}
        </div>
    );
}
