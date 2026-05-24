/**
 * Real Mapbox map for the dashboard-v2 screens. Replaces the stylized SVG
 * MapView in atoms.tsx, which was a design placeholder.
 *
 * Two modes:
 *  - Mission Control: many balloons (one per device's latest fix), plus the
 *    selected device's full track.
 *  - Device Tracker:  one balloon at the scrub time, plus the flight path
 *    truncated to the scrub time so the trail "draws in" as you scrub.
 *
 * Auto-fits the view to the data on first load and whenever the device set
 * or the active selection changes.
 *
 * Re-uses NEXT_PUBLIC_MAPBOX_TOKEN that already powers the v1 dashboard.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef, LngLatBoundsLike } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import GatewayLayer from '@/components/maps/GatewayLayer';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';

export interface V2Balloon {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number | null;
}

export interface V2FlightPoint {
    lat: number;
    lon: number;
    t: number;
}

/** A gateway's location + reception strength for the most recent uplink.
 *  Many community TTN gateways don't publish their location; those are
 *  silently omitted (we only render pins for gateways with real lat/lon). */
export interface V2Gateway {
    gateway_id: string;
    lat: number;
    lon: number;
    rssi: number | null;
    snr: number | null;
}

/** Strict WGS84 — anything else crashes Mapbox (fitBounds, layers). */
export function isValidLngLat(lat: number, lon: number): boolean {
    return Number.isFinite(lat)
        && Number.isFinite(lon)
        && lat >= -90
        && lat <= 90
        && lon >= -180
        && lon <= 180;
}

interface V2MissionMapProps {
    /** All balloons to render as markers. */
    balloons: V2Balloon[];
    /** Highlighted balloon id (rendered larger / accented). */
    activeId?: string | null;
    /** Trail for the active balloon, in chronological order. */
    flightPath?: V2FlightPoint[];
    /** When set, only flight-path points with `t <= playbackT` are drawn. */
    playbackT?: number | null;
    /** When true, the map auto-fits to the active balloon + path on changes. */
    autoFit?: boolean;
    /** Optional projection — globe is nice for a world-scale view, mercator
     *  is better when zoomed in on a single mission. */
    projection?: 'globe' | 'mercator';
    /** TTN gateways that received the most recent uplink (with locations).
     *  Rendered as pins behind a user-controlled toggle so the map stays
     *  readable when the device isn't selected. */
    gateways?: V2Gateway[];
}

function isWebGLAvailable(): boolean {
    if (typeof window === 'undefined') return false;
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
        return !!gl;
    } catch {
        return false;
    }
}

export default function V2MissionMap({
    balloons,
    activeId = null,
    flightPath = [],
    playbackT = null,
    autoFit = true,
    projection = 'globe',
    gateways = [],
}: V2MissionMapProps) {
    const mapRef = useRef<MapRef>(null);
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);
    /* Default OFF — gateway pins are powerful but visually busy when there
     * are 10+ of them. User opts in via the toolbar toggle in the upper
     * right of the map. Persistence across renders is fine; we don't try
     * to remember it across page reloads (next session starts clean). */
    const [showGateways, setShowGateways] = useState(false);

    /* Telemetry can contain legacy / corrupt rows (e.g. lng stored in lat).
     * Never pass those to Mapbox — they hard-throw inside fitBounds. */
    const validBalloons = useMemo(
        () => balloons.filter(b => isValidLngLat(b.lat, b.lon)),
        [balloons],
    );
    const validFlightPath = useMemo(
        () => flightPath.filter(p => isValidLngLat(p.lat, p.lon)),
        [flightPath],
    );
    /* Gateways without published location are omitted from the map but still
     * appear in the GatewaysPanel's list. */
    const validGateways = useMemo(
        () => gateways.filter(g => isValidLngLat(g.lat, g.lon)),
        [gateways],
    );

    useEffect(() => {
        setWebglOk(isWebGLAvailable());
    }, []);

    /* Style flag must reset when the projection forces a remount. */
    useEffect(() => { setStyleLoaded(false); }, [projection]);

    /* Initial view — center on first balloon if any, else continental US. */
    const initialView = useMemo(() => {
        const focus = validBalloons.find(b => b.id === activeId) ?? validBalloons[0];
        if (focus) {
            return { longitude: focus.lon, latitude: focus.lat, zoom: 6 };
        }
        return { longitude: -98, latitude: 39, zoom: 3.2 };
        /* eslint-disable-next-line react-hooks/exhaustive-deps */
    }, []); /* only used at mount */

    /* Auto-fit policy: fit once per activeId selection, then leave the camera
     * alone so live data updates and scrubbing don't yank the view back. The
     * user can pan / zoom freely; switching devices re-fits. */
    const fittedActiveRef = useRef<string | null | undefined>(undefined);
    useEffect(() => {
        if (!autoFit) return;
        const map = mapRef.current;
        if (!map || !styleLoaded) return;
        if (fittedActiveRef.current === (activeId ?? null)) return;

        /* Keep camera updates out of uncaught rejects from mapbox-gl. */
        try {
            const active = validBalloons.find(b => b.id === activeId);
            const lats: number[] = [];
            const lons: number[] = [];
            if (active) {
                lats.push(active.lat);
                lons.push(active.lon);
            }
            validFlightPath.forEach(p => {
                if (playbackT !== null && p.t > playbackT) return;
                lats.push(p.lat);
                lons.push(p.lon);
            });
            /* If we have no active selection, fit to the whole fleet. */
            if (lats.length === 0) {
                validBalloons.forEach(b => { lats.push(b.lat); lons.push(b.lon); });
            }
            /* No data yet — keep `fittedActiveRef` unset so we try again once
             * data arrives for this same activeId. */
            if (lats.length === 0) return;

            const minLat = Math.min(...lats);
            const maxLat = Math.max(...lats);
            const minLon = Math.min(...lons);
            const maxLon = Math.max(...lons);

            if (minLat < -90 || maxLat > 90 || minLon < -180 || maxLon > 180) return;

            if (lats.length === 1) {
                map.flyTo({
                    center: [lons[0], lats[0]],
                    zoom: 8,
                    duration: 1200,
                });
            } else {
                const bounds: LngLatBoundsLike = [[minLon, minLat], [maxLon, maxLat]];
                map.fitBounds(bounds, {
                    padding: { top: 60, bottom: 60, left: 60, right: 60 },
                    duration: 1200,
                    maxZoom: 11,
                });
            }
            fittedActiveRef.current = activeId ?? null;
        } catch (e) {
            console.warn('V2MissionMap camera update skipped', e);
        }
    }, [autoFit, styleLoaded, activeId, validBalloons, validFlightPath, playbackT]);

    const balloonGeoJSON = useMemo(() => ({
        type: 'FeatureCollection' as const,
        features: validBalloons.map(b => ({
            type: 'Feature' as const,
            id: b.id,
            geometry: { type: 'Point' as const, coordinates: [b.lon, b.lat] },
            properties: {
                deviceId: b.id,
                altitude: b.altitude_m ?? 0,
                isActive: b.id === activeId ? 1 : 0,
            },
        })),
    }), [validBalloons, activeId]);

    /* Trail: filter to playback time, then to LineString. */
    const flightPathGeoJSON = useMemo(() => {
        const pts = (playbackT === null
            ? validFlightPath
            : validFlightPath.filter(p => p.t <= playbackT)
        );
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                geometry: {
                    type: 'LineString' as const,
                    coordinates: pts.map(p => [p.lon, p.lat] as [number, number]),
                },
                properties: {},
            }],
        };
    }, [validFlightPath, playbackT]);

    /* Gateway pins — coloured by signal strength so the strongest gateways
     * (closest, best-LOS) read as accent green and the weakest (long-range,
     * just-barely-receiving) as muted amber. Reception lines are deliberately
     * thin so the balloon's flight path stays the visual primary. */
    const gatewaysGeoJSON = useMemo(() => ({
        type: 'FeatureCollection' as const,
        features: validGateways.map(g => ({
            type: 'Feature' as const,
            id: g.gateway_id,
            geometry: { type: 'Point' as const, coordinates: [g.lon, g.lat] },
            properties: {
                gateway_id: g.gateway_id,
                rssi: g.rssi ?? -130,    /* worst-case fallback for the colour ramp */
                snr: g.snr ?? -10,
            },
        })),
    }), [validGateways]);

    /* Reception lines from the active balloon to each gateway that heard it
     * — provides immediate visual confirmation of "who is listening to me
     * right now". Only drawn when an active balloon has a position. */
    const receptionLinesGeoJSON = useMemo(() => {
        const active = validBalloons.find(b => b.id === activeId);
        if (!active || validGateways.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: validGateways.map(g => ({
                type: 'Feature' as const,
                geometry: {
                    type: 'LineString' as const,
                    coordinates: [
                        [active.lon, active.lat],
                        [g.lon, g.lat],
                    ] as [number, number][],
                },
                properties: { rssi: g.rssi ?? -130 },
            })),
        };
    }, [validBalloons, activeId, validGateways]);

    if (webglOk === false) {
        return (
            <div style={{
                width: '100%', height: '100%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--sl-bg-1)', color: 'var(--sl-text-dim2)',
                fontSize: 11, padding: 24, textAlign: 'center',
            }}>
                <div>
                    <div style={{ color: 'var(--sl-alert)', marginBottom: 6, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                        Map unavailable
                    </div>
                    <div style={{ maxWidth: 360, lineHeight: 1.5 }}>
                        Browser can&apos;t create a WebGL context. Enable hardware acceleration
                        (chrome://settings/system) and reload.
                    </div>
                </div>
            </div>
        );
    }

    if (webglOk === null) {
        /* Tiny placeholder before the feature check completes. */
        return <div style={{ width: '100%', height: '100%', background: 'var(--sl-bg-1)' }} />;
    }

    /* If there's no token configured, the user gets a clear hint instead
     * of a silent blank canvas. */
    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
        return (
            <div style={{
                width: '100%', height: '100%', background: 'var(--sl-bg-1)',
                color: 'var(--sl-text-dim2)', fontSize: 11, padding: 16,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                NEXT_PUBLIC_MAPBOX_TOKEN not configured.
            </div>
        );
    }

    return (
        <div style={{ position: 'absolute', inset: 0 }}>
            <Map
                ref={mapRef}
                key={projection}
                mapboxAccessToken={token}
                initialViewState={initialView}
                style={{ width: '100%', height: '100%' }}
                mapStyle="mapbox://styles/mapbox/dark-v11"
                projection={projection === 'globe' ? 'globe' : 'mercator'}
                onLoad={() => {
                    setStyleLoaded(true);
                    const m = mapRef.current?.getMap();
                    if (m) quietBasemapLabels(m);
                }}
                onStyleData={() => {
                    setStyleLoaded(true);
                    const m = mapRef.current?.getMap();
                    if (m) quietBasemapLabels(m);
                }}
                fog={projection === 'globe' ? {
                    color: 'rgb(20, 20, 20)',
                    'high-color': 'rgb(10, 10, 10)',
                    'horizon-blend': 0.02,
                    'space-color': 'rgb(5, 5, 5)',
                    'star-intensity': 0.4,
                } : undefined}
            >
                {styleLoaded && (
                    <>
                        {/* Static TTN ground-station coverage — sits at
                          * the bottom of the layer stack so flight paths
                          * and balloon pins render on top. */}
                        <GatewayLayer />
                        {flightPathGeoJSON && (
                            <Source id="v2-flight-path" type="geojson" data={flightPathGeoJSON} lineMetrics={true}>
                                <Layer
                                    id="v2-flight-path-line"
                                    type="line"
                                    paint={{
                                        'line-width': [
                                            'interpolate', ['linear'], ['zoom'],
                                            3, 1.4,
                                            8, 2.2,
                                            14, 3.5,
                                        ],
                                        'line-opacity': 0.85,
                                        /* Fade older sections of the trail toward dim — but
                                         * keep the launch point visible. The leading edge
                                         * still reads as "now" because it's fully bright. */
                                        'line-gradient': [
                                            'interpolate', ['linear'], ['line-progress'],
                                            0,   'rgba(94, 234, 212, 0.3)',
                                            0.6, 'rgba(94, 234, 212, 0.55)',
                                            1,   'rgba(94, 234, 212, 1.0)',
                                        ],
                                    }}
                                />
                            </Source>
                        )}

                        {/* Reception lines render BEHIND the balloon/gateway pins so
                          * the pins always sit on top. */}
                        {showGateways && receptionLinesGeoJSON && (
                            <Source id="v2-reception-lines" type="geojson" data={receptionLinesGeoJSON}>
                                <Layer
                                    id="v2-reception-line"
                                    type="line"
                                    paint={{
                                        'line-color': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, 'rgba(245, 158, 11, 0.18)',  /* faint amber, weakest */
                                            -110, 'rgba(245, 158, 11, 0.45)',
                                            -100, 'rgba(94, 234, 212, 0.55)',
                                             -85, 'rgba(94, 234, 212, 0.85)',  /* bright teal, strongest */
                                        ],
                                        'line-width': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, 0.8,
                                             -85, 2.0,
                                        ],
                                    }}
                                />
                            </Source>
                        )}

                        {showGateways && validGateways.length > 0 && (
                            <Source id="v2-gateways" type="geojson" data={gatewaysGeoJSON}>
                                <Layer
                                    id="v2-gateway-pin"
                                    type="circle"
                                    paint={{
                                        'circle-color': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, '#f59e0b',   /* amber: marginal reception */
                                            -100, '#fbbf24',
                                             -90, '#a3e635',
                                             -80, '#5eead4',   /* teal: strong reception */
                                        ],
                                        'circle-radius': 5,
                                        'circle-stroke-width': 1,
                                        'circle-stroke-color': '#0b1220',
                                        'circle-stroke-opacity': 0.9,
                                    }}
                                />
                            </Source>
                        )}

                        <Source id="v2-balloons" type="geojson" data={balloonGeoJSON}>
                            <Layer
                                id="v2-balloon-halo"
                                type="circle"
                                filter={['==', ['get', 'isActive'], 1]}
                                paint={{
                                    'circle-color': 'rgba(94, 234, 212, 0.18)',
                                    'circle-radius': 18,
                                    'circle-blur': 0.6,
                                }}
                            />
                            <Layer
                                id="v2-balloon-core"
                                type="circle"
                                paint={{
                                    'circle-color': [
                                        'case', ['==', ['get', 'isActive'], 1],
                                        '#5eead4',
                                        '#6b7785',
                                    ],
                                    'circle-radius': [
                                        'case', ['==', ['get', 'isActive'], 1],
                                        7,
                                        4.5,
                                    ],
                                    'circle-stroke-width': 1,
                                    'circle-stroke-color': [
                                        'case', ['==', ['get', 'isActive'], 1],
                                        '#5eead4',
                                        '#98a2b3',
                                    ],
                                    'circle-stroke-opacity': 0.7,
                                }}
                            />
                        </Source>
                    </>
                )}
            </Map>

            {/* Toggle overlay — top-right of the map, positioned BELOW the
              * "uplink · Xm ago" Age pill that the parent screens render at
              * top:14 right:14 (z-index:1). top:50 leaves a comfortable 12px
              * gap; z-index 2 ensures clicks land on the toggle even where
              * the two layers' bounding boxes brush against each other.
              *
              * Counts the gateways that have a published location (the only
              * ones that can render as pins); the gateway list panel always
              * shows the full count. */}
            {validGateways.length > 0 && (
                <button
                    type="button"
                    onClick={() => setShowGateways(s => !s)}
                    style={{
                        position: 'absolute',
                        top: 50,
                        right: 14,
                        zIndex: 2,
                        padding: '6px 10px',
                        fontFamily: 'var(--sl-mono, monospace)',
                        fontSize: 10,
                        letterSpacing: '0.10em',
                        textTransform: 'uppercase',
                        color: showGateways ? '#0b1220' : '#cbd5e1',
                        background: showGateways ? '#5eead4' : 'rgba(11, 18, 32, 0.85)',
                        border: '1px solid ' + (showGateways ? '#5eead4' : '#334155'),
                        cursor: 'pointer',
                        backdropFilter: 'blur(4px)',
                        WebkitBackdropFilter: 'blur(4px)',
                    }}
                    aria-pressed={showGateways}
                >
                    {showGateways ? '◉' : '○'} GATEWAYS · {validGateways.length}
                </button>
            )}
        </div>
    );
}
