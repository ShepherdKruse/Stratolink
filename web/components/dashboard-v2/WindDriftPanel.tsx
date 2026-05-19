'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { V2FlightPoint } from './V2MissionMap';
import { isValidLngLat } from './V2MissionMap';
import WindParticleOverlay from './WindParticleOverlay';
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
};

export default function WindDriftPanel({
    startLat,
    startLon,
    pressureHpa,
    observedTrack = [],
    forecastHours = 24,
    showWind = true,
}: WindDriftPanelProps) {
    const mapRef = useRef<MapRef>(null);
    const [forecast, setForecast] = useState<DriftPoint[]>([]);
    const [windField, setWindField] = useState<WindField | null>(null);
    const [loading, setLoading] = useState(false);
    const [gridLoading, setGridLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadForecast = useCallback(async () => {
        if (!isValidLngLat(startLat, startLon)) return;
        setLoading(true);
        setError(null);
        try {
            const q = new URLSearchParams({
                lat: String(startLat),
                lon: String(startLon),
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
    }, [startLat, startLon, pressureHpa, forecastHours]);

    useEffect(() => {
        loadForecast();
    }, [loadForecast]);

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
        loadWindGrid();
    }, [loadWindGrid]);

    const tracks = useMemo(() => {
        const lines = [];
        if (observedTrack.length >= 2) {
            lines.push({
                coords: observedTrack.map((p) => ({ lat: p.lat, lon: p.lon })),
                color: '#e86a2a',
                width: 3,
            });
        }
        const predicted = forecast
            .filter((p) => p.source === 'predicted' || p.source === 'start')
            .map((p) => ({ lat: p.lat, lon: p.lon }));
        if (predicted.length >= 2) {
            lines.push({
                coords: predicted,
                color: '#5eead4',
                dashed: true,
                width: 2.5,
            });
        }
        return lines;
    }, [observedTrack, forecast]);

    const endPoint = forecast.length ? forecast[forecast.length - 1] : null;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || allPoints.length === 0) return;
        const lons = allPoints.map((p) => p.lon);
        const lats = allPoints.map((p) => p.lat);
        map.fitBounds(
            [
                [Math.min(...lons) - 0.6, Math.min(...lats) - 0.5],
                [Math.max(...lons) + 0.6, Math.max(...lats) + 0.5],
            ],
            { padding: 56, duration: 800 },
        );
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
                        {gridLoading ? ' · loading wind grid…' : windField ? ' · wind overlay on' : ''}
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => {
                        loadForecast();
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
                />

                <WindParticleOverlay
                    mapRef={mapRef}
                    windField={showWind ? windField : null}
                    tracks={tracks}
                    active={tracks.length > 0 || !!windField}
                />

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
                    {showWind && (
                        <div style={{ marginBottom: 6 }}>
                            <span style={{ color: 'hsl(140,70%,55%)' }}>—</span> wind speed (GFS layer)
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
