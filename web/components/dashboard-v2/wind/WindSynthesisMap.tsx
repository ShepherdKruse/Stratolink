'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import '@/styles/wind-synthesis.css';
import type { V2FlightPoint } from '../V2MissionMap';
import { isValidLngLat } from '../V2MissionMap';
import { snapPressureHpa } from '@/lib/wind/fetchWindGrid';
import { forecastWindBlobToField } from '@/lib/wind/gfsGrid';
import type { StratolinkForecast } from '@/lib/wind/forecastTypes';
import { splitTrackSegments } from '@/lib/wind/trackSegments';
import type { WindField } from '@/lib/wind/types';
import WindStreamOverlay from './WindStreamOverlay';
import WindForecastScrubber, { type HindcastScrubInfo } from './WindForecastScrubber';
import { useTickingNow } from '../shared';
import {
    buildForecastTimeline,
    positionAtTimelineMs,
} from '@/lib/wind/forecastTimeline';
import { HINDCAST_REPLAY_HOURS } from '@/lib/wind/hindcastReplay';
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
    showWind?: boolean;
    lastAltM?: number | null;
};

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

function applyForecast(
    forecast: StratolinkForecast,
    showWind: boolean,
    setMc: (v: StratolinkForecast | null) => void,
    setWindField: (v: WindField | null) => void,
) {
    setMc(forecast);
    setWindField(
        showWind
            ? forecastWindBlobToField(forecast.wind_field, forecast.generated_at, forecast.level_hpa)
            : null,
    );
}

export default function WindSynthesisMap({
    deviceId,
    callsign,
    observedTrack,
    startLat,
    startLon,
    launchLat,
    launchLon,
    pressureHpa,
    forecastHours = 24,
    anchorKey = 'default',
    telemetryReady = true,
    nullschoolUrl,
    showWind = true,
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
        showWind,
    });
    propsRef.current = {
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
        showWind,
    };
    const [mapReady, setMapReady] = useState(false);
    const [mc, setMc] = useState<StratolinkForecast | null>(null);
    const [windField, setWindField] = useState<WindField | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showEnsemble, setShowEnsemble] = useState(true);
    const [showEllipses, setShowEllipses] = useState(true);
    const [scrubMs, setScrubMs] = useState<number | null>(null);
    /** User moved the slider — do not snap back to "now" when forecast/timeline refreshes. */
    const userPinnedScrubRef = useRef(false);
    const [hindcast, setHindcast] = useState<{
        path: Array<[number, number]>;
        info: HindcastScrubInfo;
    } | null>(null);

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
            setWindField(null);
            setLoadedAnchorKey(null);
        }
        setError(null);

        const applyIfCurrent = (forecast: StratolinkForecast) => {
            if (reqId !== forecastReqRef.current) return;
            if (anchorAtStart !== anchorKeyRef.current) return;
            applyForecast(forecast, p.showWind, setMc, setWindField);
            setLoadedAnchorKey(anchorAtStart);
        };

        try {
            const first = p.observedTrack[0];
            const launch =
                p.launchLat != null && p.launchLon != null
                    ? { lat: p.launchLat, lon: p.launchLon, time_utc: obsTimeUtc(first.t) }
                    : { lat: first.lat, lon: first.lon, time_utc: obsTimeUtc(first.t) };

            const segs = splitTrackSegments(p.observedTrack);
            const driftSegment =
                segs.freezeDrift.length >= 2 ? segs.freezeDrift : undefined;

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
                    driftSegment,
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
            setWindField(null);
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

    useEffect(() => {
        if (!mc) return;
        setWindField(
            showWind ? forecastWindBlobToField(mc.wind_field, mc.generated_at, mc.level_hpa) : null,
        );
    }, [showWind, mc]);

    const segments = useMemo(() => splitTrackSegments(observedTrack), [observedTrack]);

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
        if (!forecastReady || !mc || !showEnsemble) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ensemble.map((traj) => ({
                type: 'Feature' as const,
                properties: {},
                geometry: { type: 'LineString' as const, coordinates: traj },
            })),
        };
    }, [forecastReady, mc, showEnsemble]);

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

    const driftCoords = useMemo(() => {
        if (!forecastReady) return [];
        if (mc?.observed.drift_segment?.length) return mc.observed.drift_segment;
        if (segments.freezeDrift.length) return segments.freezeDrift;
        return [];
    }, [forecastReady, mc, segments.freezeDrift]);

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
        );
    }, [timeline, forecastReady, effectiveScrubMs, observedTrack, driftCoords, nominalPath]);

    const scrubAtNow = timeline != null && Math.abs(effectiveScrubMs - timeline.tNow) < 60_000;

    const hindcastEligibility = useMemo(() => {
        if (!forecastReady || !timeline || !lastObs || scrubPosition?.segment !== 'observed') {
            return { ok: false as const, reason: null };
        }
        const fixesBefore = observedTrack.filter((p) => p.t <= effectiveScrubMs).length;
        if (fixesBefore < 2) {
            return { ok: false as const, reason: 'Need at least 2 GPS fixes before this time for bias correction.' };
        }
        const pointsAfter = observedTrack.filter((p) => p.t > effectiveScrubMs + 30_000);
        if (pointsAfter.length < 2) {
            return {
                ok: false as const,
                reason: 'Scrub earlier — need more observed GPS ahead of this point to score the replay.',
            };
        }
        const spanH = (pointsAfter[pointsAfter.length - 1].t - effectiveScrubMs) / 3_600_000;
        if (spanH < 0.5) {
            return { ok: false as const, reason: 'Not enough GPS track after this moment to validate.' };
        }
        return { ok: true as const, reason: null };
    }, [forecastReady, timeline, lastObs, scrubPosition, effectiveScrubMs, observedTrack]);

    const canHindcast = hindcastEligibility.ok;

    useEffect(() => {
        if (!canHindcast) {
            setHindcast(null);
            return;
        }
        let cancelled = false;
        setHindcast((prev) => ({
            path: prev?.path ?? [],
            info: { loading: true, nFixesUsed: prev?.info.nFixesUsed },
        }));
        const timer = setTimeout(async () => {
            try {
                const res = await fetch('/api/wind-hindcast', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    cache: 'no-store',
                    body: JSON.stringify({
                        observedTrack: observedTrack.map((p) => ({
                            lat: p.lat,
                            lon: p.lon,
                            t: p.t,
                        })),
                        anchorMs: effectiveScrubMs,
                        pressureHpa: levelHpa,
                        forecastHours: HINDCAST_REPLAY_HOURS,
                    }),
                });
                const data = await res.json();
                if (cancelled) return;
                if (!res.ok) throw new Error(data.error ?? 'Hindcast failed');
                setHindcast({
                    path: data.predicted_path as Array<[number, number]>,
                    info: {
                        loading: false,
                        nFixesUsed: data.n_fixes_used,
                        errors: data.errors,
                    },
                });
            } catch (e) {
                if (cancelled) return;
                setHindcast({
                    path: [],
                    info: {
                        loading: false,
                        error: e instanceof Error ? e.message : 'Hindcast failed',
                    },
                });
            }
        }, 450);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [canHindcast, effectiveScrubMs, observedTrack, levelHpa]);

    const hindcastLine = useMemo(
        () => (hindcast?.path.length ? lineGeoJson(hindcast.path) : null),
        [hindcast?.path],
    );

    const freezeLine = useMemo(() => lineGeoJson(driftCoords), [driftCoords]);
    const observedLine = useMemo(() => lineGeoJson(obsCoords), [obsCoords]);
    const resumedLine = useMemo(() => lineGeoJson(resumedCoords), [resumedCoords]);
    const predictedLine = useMemo(() => lineGeoJson(predCoords), [predCoords]);

    const allPoints = useMemo(() => {
        const pts = [
            ...observedTrack,
            ...nominalPath.map(([lon, lat]) => ({ lat, lon, t: '' })),
        ];
        if (e90_at_horizon?.polygon) {
            for (const [lon, lat] of e90_at_horizon.polygon) pts.push({ lat, lon, t: '' });
        }
        return pts.filter((p) => isValidLngLat(p.lat, p.lon));
    }, [observedTrack, nominalPath, e90_at_horizon]);

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
                        className={`wind-synthesis-mode-btn${showEnsemble ? ' active' : ''}`}
                        onClick={() => setShowEnsemble((v) => !v)}
                    >
                        Spaghetti
                    </button>
                    <button
                        type="button"
                        className={`wind-synthesis-mode-btn${showEllipses ? ' active' : ''}`}
                        onClick={() => setShowEllipses((v) => !v)}
                    >
                        Ellipses
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
                    mapStyle="mapbox://styles/mapbox/navigation-night-v1"
                    attributionControl={false}
                    onLoad={() => setMapReady(true)}
                >
                    {ellipses90GeoJson && (
                        <Source id="ws-e90" type="geojson" data={ellipses90GeoJson}>
                            <Layer
                                id="ws-e90-fill"
                                type="fill"
                                paint={{ 'fill-color': '#c9521f', 'fill-opacity': 0.05 }}
                            />
                            <Layer
                                id="ws-e90-stroke"
                                type="line"
                                paint={{
                                    'line-color': '#c9521f',
                                    'line-width': 1,
                                    'line-opacity': 0.3,
                                    'line-dasharray': [3, 4],
                                }}
                            />
                        </Source>
                    )}

                    {ellipses50GeoJson && (
                        <Source id="ws-e50" type="geojson" data={ellipses50GeoJson}>
                            <Layer
                                id="ws-e50-fill"
                                type="fill"
                                paint={{ 'fill-color': '#c9521f', 'fill-opacity': 0.09 }}
                            />
                            <Layer
                                id="ws-e50-stroke"
                                type="line"
                                paint={{
                                    'line-color': '#c9521f',
                                    'line-width': 1.2,
                                    'line-opacity': 0.45,
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
                                    'line-color': '#e6d088',
                                    'line-width': 1,
                                    'line-opacity': 0.07,
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
                                    'line-color': '#d4622a',
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
                                    'line-color': '#d4622a',
                                    'line-width': 2,
                                    'line-opacity': 0.75,
                                    'line-dasharray': [4, 3],
                                }}
                            />
                        </Source>
                    )}

                    {hindcastLine && (
                        <Source id="ws-hindcast" type="geojson" data={hindcastLine}>
                            <Layer
                                id="ws-hindcast-line"
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-color': '#5ec4e8',
                                    'line-width': 3.5,
                                    'line-opacity': 1,
                                    'line-dasharray': [2, 2],
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
                                    'line-color': '#c9b86a',
                                    'line-width': 2,
                                    'line-opacity': 0.88,
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
                                    'circle-color': '#e6d088',
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
                                    'text-color': 'rgba(230,208,120,.75)',
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
                                style={{ width: 11, height: 11, background: '#c9521f' }}
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
                                    background: '#e6d088',
                                    boxShadow: '0 0 0 2px rgba(8,13,23,.85)',
                                }}
                                title="Implied position now · forecast start"
                            />
                        </Marker>
                    )}

                    {scrubAtNow && forecastReady && endPoint && (
                        <Marker longitude={endPoint.lon} latitude={endPoint.lat} anchor="center">
                            <div
                                className="wind-synthesis-waypoint"
                                style={{ width: 12, height: 12, background: '#e6d088' }}
                                title="GFS endpoint"
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

                {showWind && (
                    <WindStreamOverlay
                        mapRef={mapRef}
                        windField={windField}
                        mapReady={mapReady}
                        active={!!windField}
                    />
                )}

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
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, height: 2.5, borderRadius: 2, background: '#c9521f' }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Observed GPS track</span>
                </div>
                {segments.freezeDrift.length >= 2 && (
                    <div className="wind-synthesis-lg-row">
                        <div style={{ width: 26, borderTop: '2px dashed rgba(148,162,180,.6)' }} />
                        <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>GPS-frozen drift (implied)</span>
                    </div>
                )}
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, borderTop: '2px dashed rgba(230,210,140,.8)' }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>Nominal forecast path</span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div
                        style={{
                            width: 26,
                            height: 10,
                            borderRadius: 2,
                            background: 'rgba(232,93,42,.28)',
                            border: '1px dashed rgba(255,154,92,.55)',
                        }}
                    />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>50% confidence ellipse</span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div
                        style={{
                            width: 26,
                            height: 10,
                            borderRadius: 2,
                            background: 'rgba(201,82,31,.06)',
                            border: '1px dashed rgba(201,82,31,.28)',
                        }}
                    />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>90% confidence ellipse</span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, borderTop: '1px solid rgba(230,208,136,.25)' }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>
                        {mc?.metadata.n_ensemble ?? 200} ensemble members
                    </span>
                </div>
                <div className="wind-synthesis-lg-row">
                    <div style={{ width: 26, borderTop: '2px dashed rgba(94,196,232,.95)' }} />
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>
                        Walk-forward replay (scrub observed track)
                    </span>
                </div>
            </div>

            {showWind && (
                <div className="wind-synthesis-speed-scale">
                    <div
                        style={{
                            fontSize: 9,
                            fontWeight: 600,
                            letterSpacing: '.14em',
                            textTransform: 'uppercase',
                            color: 'rgba(200,212,232,.35)',
                        }}
                    >
                        m/s
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="wind-synthesis-ss-bar" />
                        <div
                            style={{
                                display: 'flex',
                                flexDirection: 'column',
                                justifyContent: 'space-between',
                                height: 120,
                                fontFamily: 'var(--sl-mono)',
                                fontSize: 9,
                                color: 'rgba(200,212,232,.4)',
                            }}
                        >
                            <span>45</span>
                            <span>30</span>
                            <span>15</span>
                            <span>0</span>
                        </div>
                    </div>
                </div>
            )}

            {forecastReady && timeline && scrubPosition && (
                <WindForecastScrubber
                    timeline={timeline}
                    scrubMs={effectiveScrubMs}
                    onScrubMs={handleScrubMs}
                    position={scrubPosition}
                    observedTrack={observedTrack}
                    forecastHorizonH={effectiveHorizonH}
                    hindcast={
                        scrubPosition?.segment === 'observed'
                            ? canHindcast
                                ? hindcast?.info
                                : { loading: false, error: hindcastEligibility.reason ?? undefined }
                            : null
                    }
                />
            )}
        </div>
    );
}
