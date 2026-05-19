'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { V2FlightPoint } from './V2MissionMap';
import { isValidLngLat } from './V2MissionMap';
import WindParticleOverlay from './WindParticleOverlay';
import WindVectorOverlay, { type WindVizMode } from './WindVectorOverlay';
import { boundsFromPoints } from '@/lib/wind/fetchWindGrid';
import type { WindField } from '@/lib/wind/types';

type DriftPoint = {
    lat: number;
    lon: number;
    time: string;
    source: string;
    windSpeedMs?: number;
    windDirDeg?: number;
};

type WindDriftPanelProps = {
    startLat: number;
    startLon: number;
    pressureHpa: number;
    observedTrack?: V2FlightPoint[];
    forecastHours?: number;
    showWind?: boolean;
    windVizMode?: WindVizMode;
    /** When this changes (e.g. device switch), forecast re-anchors to startLat/startLon. */
    anchorKey?: string;
};

export type { WindVizMode };

export default function WindDriftPanel({
    startLat,
    startLon,
    pressureHpa,
    observedTrack = [],
    forecastHours = 24,
    showWind = true,
    windVizMode = 'vectors',
    anchorKey = 'default',
}: WindDriftPanelProps) {
    const mapRef = useRef<MapRef>(null);
    const didFitRef = useRef(false);
    const forecastOriginRef = useRef({ lat: startLat, lon: startLon });
    const [forecast, setForecast] = useState<DriftPoint[]>([]);
    const [windField, setWindField] = useState<WindField | null>(null);
    const [loading, setLoading] = useState(false);
    const [gridLoading, setGridLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [mapReady, setMapReady] = useState(false);

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
                    pressureHpa: String(pressureHpa),
                    hours: String(forecastHours),
                });
                const res = await fetch(`/api/wind-drift?${q}`);
                const data = await res.json();
                if (!res.ok) throw new Error(data.error ?? 'Forecast failed');
                setForecast(data.points ?? []);
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Forecast failed');
                setForecast([]);
            } finally {
                setLoading(false);
            }
        },
        [pressureHpa, forecastHours],
    );

    // Re-anchor forecast only on device/setting change — not on every live GPS tick
    useEffect(() => {
        if (!isValidLngLat(startLat, startLon)) return;
        forecastOriginRef.current = { lat: startLat, lon: startLon };
        loadForecast({ lat: startLat, lon: startLon });
        didFitRef.current = false;
        // eslint-disable-next-line react-hooks/exhaustive-deps -- anchorKey gates re-fetch; startLat/startLon read at trigger time only
    }, [anchorKey, loadForecast]);

    const allPoints = useMemo(() => {
        const pts: Array<{ lat: number; lon: number }> = [
            { lat: startLat, lon: startLon },
            ...observedTrack.map((p) => ({ lat: p.lat, lon: p.lon })),
            ...forecast.map((p) => ({ lat: p.lat, lon: p.lon })),
        ];
        return pts.filter((p) => isValidLngLat(p.lat, p.lon));
    }, [startLat, startLon, observedTrack, forecast]);

    const loadWindGrid = useCallback(async () => {
        if (!showWind || allPoints.length === 0) {
            setWindField(null);
            return;
        }
        setGridLoading(true);
        try {
            const b = boundsFromPoints(allPoints, 2.5);
            const q = new URLSearchParams({
                minLat: String(b.latMin),
                maxLat: String(b.latMax),
                minLon: String(b.lonMin),
                maxLon: String(b.lonMax),
                pressureHpa: String(pressureHpa),
            });
            const res = await fetch(`/api/wind-grid?${q}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error ?? 'Wind grid failed');
            setWindField(data as WindField);
        } catch {
            setWindField(null);
        } finally {
            setGridLoading(false);
        }
    }, [allPoints, pressureHpa, showWind]);

    useEffect(() => {
        const t = window.setTimeout(loadWindGrid, 1500);
        return () => window.clearTimeout(t);
    }, [loadWindGrid]);

    const observedLine = useMemo(() => {
        const coords = observedTrack.map((p) => [p.lon, p.lat] as [number, number]);
        if (coords.length < 2) return null;
        return {
            type: 'Feature' as const,
            geometry: { type: 'LineString' as const, coordinates: coords },
            properties: {},
        };
    }, [observedTrack]);

    const predictedLine = useMemo(() => {
        const coords = forecast
            .filter((p) => p.source === 'predicted' || p.source === 'start')
            .map((p) => [p.lon, p.lat] as [number, number]);
        if (coords.length < 2) return null;
        return {
            type: 'Feature' as const,
            geometry: { type: 'LineString' as const, coordinates: coords },
            properties: {},
        };
    }, [forecast]);

    const endPoint = forecast.length ? forecast[forecast.length - 1] : null;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || allPoints.length === 0 || didFitRef.current) return;
        const lons = allPoints.map((p) => p.lon);
        const lats = allPoints.map((p) => p.lat);
        map.fitBounds(
            [
                [Math.min(...lons) - 0.6, Math.min(...lats) - 0.5],
                [Math.max(...lons) + 0.6, Math.max(...lats) + 0.5],
            ],
            { padding: 56, duration: 800 },
        );
        didFitRef.current = true;
    }, [allPoints]);

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

    if (!token) {
        return <div style={{ padding: 24, color: 'var(--sl-text-dim)' }}>Mapbox token required</div>;
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderBottom: '1px solid var(--sl-border)',
                    flexShrink: 0,
                    gap: 8,
                }}
            >
                <div>
                    <div style={{ fontSize: 12, color: 'var(--sl-text-hi)', fontWeight: 500 }}>
                        Wind + drift synthesis (GFS)
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--sl-text-dim2)', marginTop: 2 }}>
                        Layer wind field with balloon advection · {forecastHours}h · {pressureHpa} hPa
                        {gridLoading
                            ? ' · loading wind…'
                            : windField
                              ? ` · ${windVizMode === 'vectors' ? 'vectors' : 'flow'}`
                              : ''}
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => {
                        didFitRef.current = false;
                        loadForecast(isValidLngLat(startLat, startLon) ? { lat: startLat, lon: startLon } : undefined);
                        loadWindGrid();
                    }}
                    disabled={loading}
                    style={{
                        fontSize: 11,
                        padding: '5px 10px',
                        background: 'var(--sl-bg-2)',
                        border: '1px solid var(--sl-border)',
                        color: 'var(--sl-text)',
                        borderRadius: 4,
                        cursor: loading ? 'wait' : 'pointer',
                    }}
                >
                    {loading ? 'Computing…' : 'Refresh'}
                </button>
            </div>

            {error && (
                <div style={{ padding: '8px 12px', fontSize: 11, color: 'var(--sl-alert)' }}>{error}</div>
            )}

            <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
                <Map
                    ref={mapRef}
                    mapboxAccessToken={token}
                    initialViewState={{
                        longitude: startLon,
                        latitude: startLat,
                        zoom: 5,
                    }}
                    style={{ width: '100%', height: '100%' }}
                    mapStyle="mapbox://styles/mapbox/dark-v11"
                    projection="mercator"
                    onLoad={() => setMapReady(true)}
                >
                    {observedLine && (
                        <Source id="wind-observed" type="geojson" data={observedLine}>
                            <Layer
                                id="wind-observed-line"
                                type="line"
                                paint={{
                                    'line-color': '#e86a2a',
                                    'line-width': 3,
                                    'line-opacity': 0.9,
                                }}
                            />
                        </Source>
                    )}
                    {predictedLine && (
                        <Source id="wind-predicted" type="geojson" data={predictedLine}>
                            <Layer
                                id="wind-predicted-halo"
                                type="line"
                                paint={{
                                    'line-color': '#5eead4',
                                    'line-width': 7,
                                    'line-opacity': 0.12,
                                }}
                            />
                            <Layer
                                id="wind-predicted-line"
                                type="line"
                                paint={{
                                    'line-color': '#5eead4',
                                    'line-width': 2.5,
                                    'line-dasharray': [2, 1.5],
                                    'line-opacity': 0.95,
                                }}
                            />
                        </Source>
                    )}
                </Map>

                {showWind && windVizMode === 'vectors' && (
                    <WindVectorOverlay
                        mapRef={mapRef}
                        windField={windField}
                        mapReady={mapReady}
                        active={!!windField}
                    />
                )}
                {showWind && windVizMode === 'flow' && (
                    <WindParticleOverlay
                        mapRef={mapRef}
                        windField={windField}
                        mapReady={mapReady}
                        active={!!windField}
                    />
                )}

                <div
                    style={{
                        position: 'absolute',
                        bottom: 10,
                        left: 10,
                        background: 'rgba(11,14,19,.92)',
                        border: '1px solid var(--sl-border)',
                        borderRadius: 6,
                        padding: '8px 10px',
                        fontSize: 10,
                        color: 'var(--sl-text-dim)',
                        lineHeight: 1.5,
                        maxWidth: 300,
                        zIndex: 3,
                    }}
                >
                    {showWind && windVizMode === 'vectors' && (
                        <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <svg width="28" height="10" aria-hidden>
                                <line x1="2" y1="5" x2="22" y2="5" stroke="rgba(186,218,236,0.9)" strokeWidth="2" />
                                <polygon points="22,5 18,2.5 18,7.5" fill="rgba(186,218,236,0.9)" />
                            </svg>
                            <span>wind — length ∝ speed</span>
                        </div>
                    )}
                    {showWind && windVizMode === 'flow' && (
                        <div style={{ marginBottom: 6 }}>
                            <span style={{ color: 'rgba(130,168,186,0.7)' }}>—</span> wind flow (GFS)
                        </div>
                    )}
                    <div>
                        <span style={{ color: '#e86a2a' }}>—</span> observed track
                    </div>
                    <div>
                        <span style={{ color: '#5eead4' }}>- -</span> predicted drift
                    </div>
                    {endPoint && (
                        <div style={{ marginTop: 6, fontFamily: 'var(--sl-mono)', color: 'var(--sl-text)' }}>
                            +{forecastHours}h → {endPoint.lat.toFixed(2)}°, {endPoint.lon.toFixed(2)}°
                            {endPoint.windSpeedMs != null && (
                                <>
                                    <br />
                                    wind {endPoint.windSpeedMs.toFixed(1)} m/s @ {endPoint.windDirDeg}°
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
