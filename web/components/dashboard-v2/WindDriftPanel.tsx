'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Map, { Layer, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { V2FlightPoint } from './V2MissionMap';
import { isValidLngLat } from './V2MissionMap';

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
};

export default function WindDriftPanel({
    startLat,
    startLon,
    pressureHpa,
    observedTrack = [],
    forecastHours = 24,
}: WindDriftPanelProps) {
    const mapRef = useRef<MapRef>(null);
    const [forecast, setForecast] = useState<DriftPoint[]>([]);
    const [loading, setLoading] = useState(false);
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

    const observedLine = useMemo(() => {
        const coords = observedTrack.map((p) => [p.lon, p.lat] as [number, number]);
        if (coords.length < 2) return null;
        return {
            type: 'Feature' as const,
            geometry: { type: 'LineString' as const, coordinates: coords },
            properties: {},
        };
    }, [observedTrack]);

    const endPoint = forecast.length ? forecast[forecast.length - 1] : null;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || !isValidLngLat(startLat, startLon)) return;
        const lons = [startLon, ...forecast.map((p) => p.lon)];
        const lats = [startLat, ...forecast.map((p) => p.lat)];
        if (lons.length < 1) return;
        map.fitBounds(
            [
                [Math.min(...lons) - 0.8, Math.min(...lats) - 0.6],
                [Math.max(...lons) + 0.8, Math.max(...lats) + 0.6],
            ],
            { padding: 48, duration: 800 },
        );
    }, [startLat, startLon, forecast]);

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

    if (!token) {
        return (
            <div style={{ padding: 24, color: 'var(--sl-text-dim)' }}>Mapbox token required</div>
        );
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
                        Drift forecast (GFS)
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--sl-text-dim2)', marginTop: 2 }}>
                        Balloon advected with layer wind · {forecastHours}h · {pressureHpa} hPa · 30 min steps
                    </div>
                </div>
                <button
                    type="button"
                    onClick={loadForecast}
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
                >
                    {observedLine && (
                        <Source id="observed-track" type="geojson" data={observedLine}>
                            <Layer
                                id="observed-line"
                                type="line"
                                paint={{
                                    'line-color': '#c9521f',
                                    'line-width': 2.5,
                                    'line-opacity': 0.85,
                                }}
                            />
                        </Source>
                    )}
                    {predictedLine && (
                        <Source id="predicted-track" type="geojson" data={predictedLine}>
                            <Layer
                                id="predicted-halo"
                                type="line"
                                paint={{
                                    'line-color': '#5eead4',
                                    'line-width': 8,
                                    'line-opacity': 0.15,
                                }}
                            />
                            <Layer
                                id="predicted-line"
                                type="line"
                                paint={{
                                    'line-color': '#5eead4',
                                    'line-width': 2.5,
                                    'line-dasharray': [2, 1.5],
                                    'line-opacity': 0.9,
                                }}
                            />
                        </Source>
                    )}
                </Map>

                <div
                    style={{
                        position: 'absolute',
                        bottom: 10,
                        left: 10,
                        background: 'rgba(11,14,19,.9)',
                        border: '1px solid var(--sl-border)',
                        borderRadius: 6,
                        padding: '8px 10px',
                        fontSize: 10,
                        color: 'var(--sl-text-dim)',
                        lineHeight: 1.5,
                        maxWidth: 280,
                    }}
                >
                    <div>
                        <span style={{ color: '#c9521f' }}>—</span> observed track
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
