'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import '@/styles/wind-synthesis.css';
import type { V2FlightPoint } from '../V2MissionMap';
import { isValidLngLat } from '../V2MissionMap';
import { boundsFromPoints, snapPressureHpa } from '@/lib/wind/fetchWindGrid';
import type { EnsembleMember } from '@/lib/wind/driftEnsemble';
import { splitTrackSegments } from '@/lib/wind/trackSegments';
import type { WindField } from '@/lib/wind/types';
import WindStreamOverlay from './WindStreamOverlay';
import WindVectorOverlay from '../WindVectorOverlay';

export type WindDisplayMode = 'stream' | 'vector';

type DriftPoint = {
    lat: number;
    lon: number;
    time: string;
    source: string;
    windSpeedMs?: number;
    windDirDeg?: number;
};

export type WindSynthesisMapProps = {
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

export default function WindSynthesisMap({
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
    const [mode, setMode] = useState<WindDisplayMode>('vector');
    const [forecast, setForecast] = useState<DriftPoint[]>([]);
    const [ensemble, setEnsemble] = useState<EnsembleMember[]>([]);
    const [ensembleCone, setEnsembleCone] = useState<Array<[number, number]>>([]);
    const [windField, setWindField] = useState<WindField | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const levelHpa = snapPressureHpa(pressureHpa);

    const loadForecast = useCallback(
        async (origin?: { lat: number; lon: number }) => {
            const lat = origin?.lat ?? forecastOriginRef.current.lat;
            const lon = origin?.lon ?? forecastOriginRef.current.lon;
            if (!isValidLngLat(lat, lon)) return;
            forecastOriginRef.current = { lat, lon };
            setLoading(true);
            setError(null);
            try {
                const q = new URLSearchParams({
                    lat: String(lat),
                    lon: String(lon),
                    pressureHpa: String(levelHpa),
                    hours: String(forecastHours),
                });
                const res = await fetch(`/api/wind-drift?${q}`);
                const data = await res.json();
                if (!res.ok) throw new Error(data.error ?? 'Forecast failed');
                setForecast(data.points ?? []);
                setEnsemble(data.ensemble ?? []);
                setEnsembleCone(data.cone ?? []);
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Forecast failed');
                setForecast([]);
                setEnsemble([]);
                setEnsembleCone([]);
            } finally {
                setLoading(false);
            }
        },
        [levelHpa, forecastHours],
    );

    useEffect(() => {
        if (!isValidLngLat(startLat, startLon)) return;
        forecastOriginRef.current = { lat: startLat, lon: startLon };
        loadForecast({ lat: startLat, lon: startLon });
        didFitRef.current = false;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [anchorKey, loadForecast]);

    const segments = useMemo(() => splitTrackSegments(observedTrack), [observedTrack]);

    const predCoords = useMemo(() => {
        return forecast
            .filter((p) => p.source === 'predicted' || p.source === 'start')
            .map((p) => [p.lon, p.lat] as [number, number]);
    }, [forecast]);

    const conePolygon = useMemo(() => {
        const ring = ensembleCone.length >= 4 ? ensembleCone : [];
        if (ring.length < 4) return null;
        return {
            type: 'Feature' as const,
            geometry: { type: 'Polygon' as const, coordinates: [ring] },
            properties: {},
        };
    }, [ensembleCone]);

    const ensembleLinesGeoJson = useMemo(() => {
        const features = ensemble
            .map((m) => {
                const coords = m.points.map((p) => [p.lon, p.lat] as [number, number]);
                if (coords.length < 2) return null;
                return {
                    type: 'Feature' as const,
                    geometry: { type: 'LineString' as const, coordinates: coords },
                    properties: {},
                };
            })
            .filter((f): f is NonNullable<typeof f> => f !== null);
        return features.length ? { type: 'FeatureCollection' as const, features } : null;
    }, [ensemble]);

    const hourLabels = useMemo(() => {
        const step = 4;
        const features = forecast
            .map((p, i) => ({ p, i }))
            .filter(({ i }) => i % step === 0)
            .map(({ p, i }) => ({
                type: 'Feature' as const,
                properties: { label: `+${Math.round((i * 30) / 60)}h` },
                geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] },
            }));
        return { type: 'FeatureCollection' as const, features };
    }, [forecast]);

    const loadWindGrid = useCallback(async () => {
        if (!showWind) {
            setWindField(null);
            return;
        }
        const pts = [
            ...observedTrack.map((p) => ({ lat: p.lat, lon: p.lon })),
            ...forecast.map((p) => ({ lat: p.lat, lon: p.lon })),
            ...ensemble.flatMap((m) => m.points.map((p) => ({ lat: p.lat, lon: p.lon }))),
        ];
        if (pts.length === 0) return;
        try {
            const b = boundsFromPoints(pts, 3);
            const q = new URLSearchParams({
                minLat: String(b.latMin),
                maxLat: String(b.latMax),
                minLon: String(b.lonMin),
                maxLon: String(b.lonMax),
                pressureHpa: String(levelHpa),
            });
            const res = await fetch(`/api/wind-grid?${q}`);
            const data = await res.json();
            if (res.ok) setWindField(data as WindField);
        } catch {
            setWindField(null);
        }
    }, [observedTrack, forecast, ensemble, levelHpa, showWind]);

    useEffect(() => {
        if (!mapReady) return;
        const t = window.setTimeout(loadWindGrid, 300);
        return () => window.clearTimeout(t);
    }, [loadWindGrid, mapReady]);

    const firstObs = observedTrack[0];
    const lastObs = observedTrack.length ? observedTrack[observedTrack.length - 1] : null;
    const endPoint = forecast.length ? forecast[forecast.length - 1] : null;

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

    const allPoints = useMemo(() => {
        const pts = [...observedTrack, ...forecast.map((p) => ({ lat: p.lat, lon: p.lon, t: p.time }))];
        return pts.filter((p) => isValidLngLat(p.lat, p.lon));
    }, [observedTrack, forecast]);

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

    const obsCoords = segments.observed.map((p) => [p.lon, p.lat] as [number, number]);
    const resumedCoords = segments.resumed.map((p) => [p.lon, p.lat] as [number, number]);

    const freezeLine = useMemo(() => lineGeoJson(segments.freezeDrift), [segments.freezeDrift]);
    const observedLine = useMemo(() => lineGeoJson(obsCoords), [obsCoords]);
    const resumedLine = useMemo(() => lineGeoJson(resumedCoords), [resumedCoords]);
    const predictedLine = useMemo(() => lineGeoJson(predCoords), [predCoords]);

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
        return <div style={{ padding: 24, color: 'var(--sl-text-dim)' }}>Mapbox token required</div>;
    }

    return (
        <div className="wind-synthesis-root">
            <div className="wind-synthesis-topbar">
                <div className="wind-synthesis-brand">
                    <div className="wind-synthesis-eyebrow">
                        Stratolink · Wind + Drift Synthesis · GFS {levelHpa} hPa
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
                            <b>Forecast</b> +{forecastHours}h from last fix · endpoint{' '}
                            {endPoint.lat.toFixed(2)}°N {Math.abs(endPoint.lon).toFixed(2)}°W
                        </div>
                    )}
                </div>
                <div className="wind-synthesis-spacer" />
                <div className="wind-synthesis-mode-toggle">
                    <button
                        type="button"
                        className={`wind-synthesis-mode-btn${mode === 'stream' ? ' active' : ''}`}
                        onClick={() => setMode('stream')}
                    >
                        Stream
                    </button>
                    <button
                        type="button"
                        className={`wind-synthesis-mode-btn${mode === 'vector' ? ' active' : ''}`}
                        onClick={() => setMode('vector')}
                    >
                        Vectors
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
                        loadForecast(isValidLngLat(startLat, startLon) ? { lat: startLat, lon: startLon } : undefined);
                        loadWindGrid();
                    }}
                >
                    {loading ? '…' : 'Refresh'}
                </button>
            </div>

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
                    {conePolygon && (
                        <Source id="ws-cone" type="geojson" data={conePolygon}>
                            <Layer
                                id="ws-cone-fill"
                                type="fill"
                                paint={{ 'fill-color': '#e85d2a', 'fill-opacity': 0.2 }}
                            />
                            <Layer
                                id="ws-cone-stroke"
                                type="line"
                                paint={{
                                    'line-color': '#ff9a5c',
                                    'line-width': 1.5,
                                    'line-opacity': 0.55,
                                    'line-dasharray': [4, 4],
                                }}
                            />
                        </Source>
                    )}

                    {ensembleLinesGeoJson && (
                        <Source id="ws-ensemble" type="geojson" data={ensembleLinesGeoJson}>
                            <Layer
                                id="ws-ensemble-lines"
                                type="line"
                                paint={{
                                    'line-color': 'rgba(230, 208, 136, 0.45)',
                                    'line-width': 1.5,
                                    'line-opacity': 0.7,
                                    'line-dasharray': [2, 3],
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
                                id="ws-observed-halo"
                                type="line"
                                paint={{
                                    'line-color': '#000000',
                                    'line-width': 10,
                                    'line-opacity': 0.45,
                                }}
                            />
                            <Layer
                                id="ws-observed-line"
                                type="line"
                                paint={{
                                    'line-color': '#e86a2a',
                                    'line-width': 4,
                                    'line-opacity': 0.95,
                                }}
                            />
                        </Source>
                    )}

                    {resumedLine && (
                        <Source id="ws-resumed" type="geojson" data={resumedLine}>
                            <Layer
                                id="ws-resumed-line"
                                type="line"
                                paint={{
                                    'line-color': '#e86a2a',
                                    'line-width': 3,
                                    'line-opacity': 0.9,
                                    'line-dasharray': [5, 4],
                                }}
                            />
                        </Source>
                    )}

                    {predictedLine && (
                        <Source id="ws-predicted" type="geojson" data={predictedLine}>
                            <Layer
                                id="ws-predicted-halo"
                                type="line"
                                paint={{
                                    'line-color': '#000000',
                                    'line-width': 14,
                                    'line-opacity': 0.5,
                                }}
                            />
                            <Layer
                                id="ws-predicted-line"
                                type="line"
                                paint={{
                                    'line-color': '#f5e6a8',
                                    'line-width': 4,
                                    'line-opacity': 0.95,
                                    'line-dasharray': [6, 5],
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
                                title="Last fix · prediction start"
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

                {showWind && mode === 'stream' && (
                    <WindStreamOverlay
                        mapRef={mapRef}
                        windField={windField}
                        mapReady={mapReady}
                        active={!!windField}
                    />
                )}
                {showWind && mode === 'vector' && (
                    <WindVectorOverlay
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
                    <div className="wind-synthesis-ip-header">GFS +{forecastHours}h prediction</div>
                    {endPoint && (
                        <>
                            <div className="wind-synthesis-ip-row">
                                <span className="wind-synthesis-ip-key">Predicted position</span>
                                <span className="wind-synthesis-ip-val wind-synthesis-ip-accent">
                                    {fmtCoord(endPoint.lat, endPoint.lon)}
                                </span>
                            </div>
                            {endPoint.windSpeedMs != null && (
                                <div className="wind-synthesis-ip-row">
                                    <span className="wind-synthesis-ip-key">Wind at endpoint</span>
                                    <span className="wind-synthesis-ip-val">
                                        {endPoint.windSpeedMs.toFixed(1)} m/s · {endPoint.windDirDeg}°
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
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>GFS predicted path</span>
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
                    <span style={{ fontSize: 11.5, color: 'rgba(200,212,232,.58)' }}>
                        Ensemble spread (±10% speed, ±15° dir, grid)
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
