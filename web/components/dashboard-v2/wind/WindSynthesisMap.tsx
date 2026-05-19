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
    nullschoolUrl,
    showWind = true,
    lastAltM = null,
}: WindSynthesisMapProps) {
    const mapRef = useRef<MapRef>(null);
    const didFitRef = useRef(false);
    const forecastOriginRef = useRef({ lat: startLat, lon: startLon });
    const [mapReady, setMapReady] = useState(false);
    const [mc, setMc] = useState<StratolinkForecast | null>(null);
    const [windField, setWindField] = useState<WindField | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showEnsemble, setShowEnsemble] = useState(true);
    const [showEllipses, setShowEllipses] = useState(true);

    const levelHpa = snapPressureHpa(pressureHpa);

    const loadForecast = useCallback(async () => {
        if (observedTrack.length < 1 || !isValidLngLat(startLat, startLon)) return;
        forecastOriginRef.current = { lat: startLat, lon: startLon };
        setLoading(true);
        setError(null);
        try {
            const first = observedTrack[0];
            const launch =
                launchLat != null && launchLon != null
                    ? { lat: launchLat, lon: launchLon, time_utc: first.t }
                    : { lat: first.lat, lon: first.lon, time_utc: first.t };

            const segs = splitTrackSegments(observedTrack);
            const driftSegment =
                segs.freezeDrift.length >= 2 ? segs.freezeDrift : undefined;

            const cached = await fetch(
                `/api/forecast?device=${encodeURIComponent(deviceId)}&hours=${forecastHours}`,
            );
            if (cached.ok) {
                const forecast = (await cached.json()) as StratolinkForecast;
                const cachedHours = forecast.forecast_horizon_h ?? 24;
                // Blob cache ignores ?hours= — skip short caches when UI asks for a longer horizon.
                if (cachedHours >= forecastHours) {
                    applyForecast(forecast, showWind, setMc, setWindField);
                    return;
                }
            }

            const res = await fetch('/api/wind-forecast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    deviceId,
                    mission: callsign,
                    launch,
                    observedTrack: observedTrack.map((p) => ({
                        lat: p.lat,
                        lon: p.lon,
                        t: p.t,
                        alt_m: lastAltM,
                    })),
                    driftSegment,
                    pressureHpa: levelHpa,
                    forecastHours,
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error ?? 'Forecast failed');
            applyForecast(data as StratolinkForecast, showWind, setMc, setWindField);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Forecast failed');
            setMc(null);
            setWindField(null);
        } finally {
            setLoading(false);
        }
    }, [
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
    ]);

    useEffect(() => {
        if (!isValidLngLat(startLat, startLon) || observedTrack.length < 1) return;
        loadForecast();
        didFitRef.current = false;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [anchorKey, loadForecast]);

    useEffect(() => {
        if (!mc) return;
        setWindField(
            showWind ? forecastWindBlobToField(mc.wind_field, mc.generated_at, mc.level_hpa) : null,
        );
    }, [showWind, mc]);

    const segments = useMemo(() => splitTrackSegments(observedTrack), [observedTrack]);

    const nominalPath = mc?.nominal_path ?? [];
    const predCoords = nominalPath;
    /** Hours actually in the loaded forecast (path is one point per hour from origin). */
    const effectiveHorizonH =
        mc?.forecast_horizon_h ??
        (nominalPath.length > 1 ? nominalPath.length - 1 : forecastHours);

    const ellipses90GeoJson = useMemo(() => {
        if (!mc || !showEllipses) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ellipses.map((e) => ({
                type: 'Feature' as const,
                properties: { t_hours: e.t_hours },
                geometry: { type: 'Polygon' as const, coordinates: [e.e90.polygon] },
            })),
        };
    }, [mc, showEllipses]);

    const ellipses50GeoJson = useMemo(() => {
        if (!mc || !showEllipses) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ellipses.map((e) => ({
                type: 'Feature' as const,
                properties: { t_hours: e.t_hours },
                geometry: { type: 'Polygon' as const, coordinates: [e.e50.polygon] },
            })),
        };
    }, [mc, showEllipses]);

    const ensembleGeoJson = useMemo(() => {
        if (!mc || !showEnsemble) return null;
        return {
            type: 'FeatureCollection' as const,
            features: mc.ensemble.map((traj) => ({
                type: 'Feature' as const,
                properties: {},
                geometry: { type: 'LineString' as const, coordinates: traj },
            })),
        };
    }, [mc, showEnsemble]);

    const hourLabels = useMemo(() => {
        if (!nominalPath.length) return { type: 'FeatureCollection' as const, features: [] };
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
    const endPoint = mc?.endpoint ?? null;
    const e90_at_horizon =
        mc?.ellipses.find((e) => e.t_hours === effectiveHorizonH)?.e90 ??
        mc?.ellipses[mc.ellipses.length - 1]?.e90;

    const launch = useMemo(() => {
        if (launchLat != null && launchLon != null) return { lat: launchLat, lon: launchLon };
        if (firstObs) return { lat: firstObs.lat, lon: firstObs.lon };
        return null;
    }, [launchLat, launchLon, firstObs]);

    const gpsMarkers = useMemo(() => {
        const pts = segments.resumed.length > 1 ? segments.resumed : [];
        if (pts.length === 0) return [];
        const max = 6;
        const step = Math.max(1, Math.floor(pts.length / max));
        return pts
            .filter((_, i) => i % step === 0 || i === pts.length - 1)
            .slice(0, max)
            .map((p, idx) => ({ ...p, n: idx + 1 }));
    }, [segments.resumed]);

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

    const obsCoords = useMemo(() => {
        if (mc?.observed.track?.length) return mc.observed.track;
        return segments.observed.map((p) => [p.lon, p.lat] as [number, number]);
    }, [mc, segments.observed]);

    const resumedCoords = segments.resumed.map((p) => [p.lon, p.lat] as [number, number]);

    const driftCoords = useMemo(() => {
        if (mc?.observed.drift_segment?.length) return mc.observed.drift_segment;
        return segments.freezeDrift;
    }, [mc, segments.freezeDrift]);

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
        if (!map || allPoints.length === 0 || didFitRef.current) return;
        const lons = allPoints.map((p) => p.lon);
        const lats = allPoints.map((p) => p.lat);
        map.fitBounds(
            [
                [Math.min(...lons) - 0.8, Math.min(...lats) - 0.6],
                [Math.max(...lons) + 0.8, Math.max(...lats) + 0.5],
            ],
            { padding: { top: 70, bottom: 40, left: 280, right: 120 }, duration: 900 },
        );
        didFitRef.current = true;
    }, [allPoints]);

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
                    {endPoint && (
                        <div>
                            <b>Forecast</b>{' '}
                            {mc?.stale_gps ? (
                                <>
                                    +{effectiveHorizonH}h from implied now ({mc.stale_gps.gap_hours}h since
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

            {mc?.stale_gps && (
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
                        UTC · <b>{mc.stale_gps.gap_hours}h</b> integrated with GFS at fix time · forward
                        forecast from implied position
                    </div>
                </div>
            )}

            {mc && mc.bias_correction.n_samples > 0 && (
                <div className="wind-synthesis-bias-banner">
                    <div className="wind-synthesis-bias-label">Forecast calibrated with in-flight data</div>
                    <div className="wind-synthesis-bias-body">
                        Speed ×<b>{mc.bias_correction.speed_factor}</b> · direction{' '}
                        <b>
                            {mc.bias_correction.direction_offset_deg > 0 ? '+' : ''}
                            {mc.bias_correction.direction_offset_deg}°
                        </b>
                        {mc.bias_correction.capped ? ' (capped)' : ''}
                    </div>
                </div>
            )}

            {error && (
                <div style={{ position: 'absolute', top: 58, left: 20, zIndex: 25, fontSize: 11, color: '#f87171' }}>
                    {error}
                </div>
            )}

            <div className="wind-synthesis-map">
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

                    {mc?.stale_gps && mc.forecast_origin && (
                        <Marker
                            longitude={mc.forecast_origin.lon}
                            latitude={mc.forecast_origin.lat}
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

                    {endPoint && (
                        <Marker longitude={endPoint.lon} latitude={endPoint.lat} anchor="center">
                            <div
                                className="wind-synthesis-waypoint"
                                style={{ width: 12, height: 12, background: '#e6d088' }}
                                title="GFS endpoint"
                            />
                        </Marker>
                    )}

                    {gpsMarkers.map((g) => (
                        <Marker key={`${g.lon}-${g.lat}-${g.n}`} longitude={g.lon} latitude={g.lat} anchor="center">
                            <div className="wind-synthesis-gps-marker">{g.n}</div>
                        </Marker>
                    ))}
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
                    {endPoint && (
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
                {gpsMarkers.length > 0 && (
                    <div
                        className="wind-synthesis-lg-row"
                        style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,.06)' }}
                    >
                        <div
                            style={{
                                width: 9,
                                height: 9,
                                borderRadius: '50%',
                                background: '#5065b8',
                                border: '1.5px solid rgba(255,255,255,.7)',
                            }}
                        />
                        <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>
                            GPS position updates (×{gpsMarkers.length})
                        </span>
                    </div>
                )}
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
        </div>
    );
}
