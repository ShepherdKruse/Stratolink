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
import GatewayRangeRings from '@/components/maps/GatewayRangeRings';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';
import { ringKm } from '@/lib/gateways/range';

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
    /** When set, switches to the balloon-centered range view: the ambient
     *  coverage field is replaced by spreading-factor rings around this
     *  point, and the camera fits to the SF12 ring instead of the track. */
    rangeCenter?: { lat: number; lon: number; altM: number | null } | null;
    /** When true, render each transmitted GPS fix as a small dot in addition
     *  to the connecting flown-path line — distinguishing "where the balloon
     *  reported its position" from "where we think it flew between". */
    showTransmitPoints?: boolean;
    /** Predicted next track as [lon, lat] pairs (nominal forecast). Drawn as a
     *  dashed line ahead of the last fix. Empty / omitted = nothing drawn. */
    forecastPath?: Array<[number, number]>;
    /** Monte-Carlo ensemble members, each a [lon, lat] track — drawn as faint
     *  "spaghetti" behind the nominal line. */
    forecastEnsemble?: Array<Array<[number, number]>>;
    /** Per-slice 50/90% confidence ellipse polygons — drawn as the cone. */
    forecastEllipses?: Array<{ e50: Array<[number, number]>; e90: Array<[number, number]> }>;
    /** Wind-reconstructed likely prior path ([lon, lat]) — the hindcast. */
    hindcastPath?: Array<[number, number]>;
    /** Two-point gray connector from the last fix to the assumed-now position
     *  while GPS is stale. Null / omitted = nothing drawn. */
    staleLine?: Array<[number, number]> | null;
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
    rangeCenter = null,
    showTransmitPoints = false,
    forecastPath = [],
    forecastEnsemble = [],
    forecastEllipses = [],
    hindcastPath = [],
    staleLine = null,
}: V2MissionMapProps) {
    const mapRef = useRef<MapRef>(null);
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);

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
        /* Range mode owns the camera — skip the track fit so the two don't
         * fight. Reset the ref so exiting range mode re-fits to the track. */
        if (rangeCenter) {
            fittedActiveRef.current = undefined;
            return;
        }
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
    }, [autoFit, styleLoaded, activeId, validBalloons, validFlightPath, playbackT, rangeCenter]);

    /* Range-mode camera: fit to the SF12 ring around the balloon. Keyed on
     * activeId so it fits once on entering range mode (and on device change),
     * not on every scrub tick — the user can then pan / zoom freely. */
    const rangeFittedRef = useRef<string | null>(null);
    useEffect(() => {
        if (!rangeCenter) {
            rangeFittedRef.current = null;
            return;
        }
        const map = mapRef.current;
        if (!map || !styleLoaded) return;
        const key = activeId ?? 'range';
        if (rangeFittedRef.current === key) return;
        try {
            const maxKm = ringKm('sf12', rangeCenter.altM);
            const r = Number.isFinite(maxKm) ? maxKm : 600;
            const latPad = r / 111;
            const lonPad = r / (111 * Math.max(0.2, Math.cos((rangeCenter.lat * Math.PI) / 180)));
            const minLon = rangeCenter.lon - lonPad;
            const maxLon = rangeCenter.lon + lonPad;
            const minLat = rangeCenter.lat - latPad;
            const maxLat = rangeCenter.lat + latPad;
            if (minLat < -90 || maxLat > 90 || minLon < -180 || maxLon > 180) return;
            map.fitBounds([[minLon, minLat], [maxLon, maxLat]] as LngLatBoundsLike, {
                padding: 50,
                duration: 800,
                maxZoom: 11,
            });
            rangeFittedRef.current = key;
        } catch (e) {
            console.warn('V2MissionMap range fit skipped', e);
        }
    }, [rangeCenter, styleLoaded, activeId]);

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

    /* Transmitted-position dots — one per GPS fix (respecting playback time).
     * These are the raw points the balloon actually reported; the flown-path
     * line above interpolates between them. */
    const transmitPointsGeoJSON = useMemo(() => {
        const pts = (playbackT === null
            ? validFlightPath
            : validFlightPath.filter(p => p.t <= playbackT)
        );
        if (pts.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: pts.map(p => ({
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] as [number, number] },
                properties: {},
            })),
        };
    }, [validFlightPath, playbackT]);

    /* Forecast line — predicted nominal track ahead of the last fix. Filtered
     * to valid WGS84 so a bad endpoint can't crash Mapbox. */
    const forecastGeoJSON = useMemo(() => {
        const pts = forecastPath.filter(([lon, lat]) => isValidLngLat(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                geometry: { type: 'LineString' as const, coordinates: pts },
                properties: {},
            }],
        };
    }, [forecastPath]);

    /* Hindcast — the wind-reconstructed likely path through GPS gaps. */
    const hindcastGeoJSON = useMemo(() => {
        const pts = hindcastPath.filter(([lon, lat]) => isValidLngLat(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: pts }, properties: {} }],
        };
    }, [hindcastPath]);

    /* Stale-GPS connector — last real fix → dead-reckoned "assumed now". */
    const staleLineGeoJSON = useMemo(() => {
        const pts = (staleLine ?? []).filter(([lon, lat]) => isValidLngLat(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: pts }, properties: {} }],
        };
    }, [staleLine]);

    /* Ensemble "spaghetti" — every Monte-Carlo member as a faint line. */
    const ensembleGeoJSON = useMemo(() => {
        const tracks = forecastEnsemble
            .map(t => t.filter(([lon, lat]) => isValidLngLat(lat, lon)))
            .filter(t => t.length >= 2);
        if (tracks.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: tracks.map(t => ({
                type: 'Feature' as const,
                geometry: { type: 'LineString' as const, coordinates: t },
                properties: {},
            })),
        };
    }, [forecastEnsemble]);

    /* Confidence cones — 50% and 90% ellipse polygons per forecast slice.
     * A polygon needs ≥3 points and a closed ring; Mapbox closes it for us. */
    const ellipsePolys = useMemo(() => {
        const e50: Array<[number, number][]> = [];
        const e90: Array<[number, number][]> = [];
        for (const slice of forecastEllipses) {
            const p50 = slice.e50.filter(([lon, lat]) => isValidLngLat(lat, lon));
            const p90 = slice.e90.filter(([lon, lat]) => isValidLngLat(lat, lon));
            if (p50.length >= 3) e50.push(p50);
            if (p90.length >= 3) e90.push(p90);
        }
        const toFC = (rings: Array<[number, number][]>) => rings.length === 0 ? null : ({
            type: 'FeatureCollection' as const,
            features: rings.map(ring => ({
                type: 'Feature' as const,
                geometry: { type: 'Polygon' as const, coordinates: [ring] },
                properties: {},
            })),
        });
        return { e50: toFC(e50), e90: toFC(e90) };
    }, [forecastEllipses]);

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
                          * and balloon pins render on top. In range mode the
                          * ambient field is replaced by balloon-centered SF
                          * rings + nearby gateways. */}
                        {rangeCenter ? (
                            <GatewayRangeRings
                                lat={rangeCenter.lat}
                                lon={rangeCenter.lon}
                                altM={rangeCenter.altM}
                            />
                        ) : (
                            <GatewayLayer />
                        )}
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

                        {/* Hindcast — wind-reconstructed likely prior path
                          * (greenish, dashed). Sits over the raw flown line so
                          * it reads as the better estimate through GPS gaps. */}
                        {hindcastGeoJSON && (
                            <Source id="v2-hindcast" type="geojson" data={hindcastGeoJSON}>
                                <Layer
                                    id="v2-hindcast-line"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{
                                        'line-color': '#3fb8a0',
                                        'line-width': 2,
                                        'line-dasharray': [2, 2],
                                        'line-opacity': 0.55,
                                    }}
                                />
                            </Source>
                        )}

                        {/* Stale-GPS connector — last real fix → dead-reckoned
                          * "assumed now", drawn gray so it reads as inferred. */}
                        {staleLineGeoJSON && (
                            <Source id="v2-stale-line" type="geojson" data={staleLineGeoJSON}>
                                <Layer
                                    id="v2-stale-line-stroke"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{
                                        'line-color': 'rgba(160, 175, 195, 0.9)',
                                        'line-width': 2,
                                        'line-dasharray': [3, 3],
                                        'line-opacity': 0.8,
                                    }}
                                />
                            </Source>
                        )}

                        {/* Confidence cone — 90% ellipses (dashed outline) then
                          * 50% ellipses (filled), so the spread reads from wide
                          * to tight. Drawn first so everything else sits on top. */}
                        {ellipsePolys.e90 && (
                            <Source id="v2-forecast-e90" type="geojson" data={ellipsePolys.e90}>
                                <Layer
                                    id="v2-forecast-e90-stroke"
                                    type="line"
                                    paint={{
                                        'line-color': '#f59e0b',
                                        'line-width': 1,
                                        'line-opacity': 0.4,
                                        'line-dasharray': [3, 4],
                                    }}
                                />
                            </Source>
                        )}
                        {ellipsePolys.e50 && (
                            <Source id="v2-forecast-e50" type="geojson" data={ellipsePolys.e50}>
                                <Layer
                                    id="v2-forecast-e50-fill"
                                    type="fill"
                                    paint={{ 'fill-color': '#f59e0b', 'fill-opacity': 0.1 }}
                                />
                                <Layer
                                    id="v2-forecast-e50-stroke"
                                    type="line"
                                    paint={{ 'line-color': '#f59e0b', 'line-width': 1, 'line-opacity': 0.5 }}
                                />
                            </Source>
                        )}

                        {/* Ensemble spaghetti — faint individual Monte-Carlo runs. */}
                        {ensembleGeoJSON && (
                            <Source id="v2-forecast-ensemble" type="geojson" data={ensembleGeoJSON}>
                                <Layer
                                    id="v2-forecast-ensemble-lines"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{ 'line-color': '#f59e0b', 'line-width': 1, 'line-opacity': 0.08 }}
                                />
                            </Source>
                        )}

                        {/* Forecast — predicted nominal track, dashed + amber so
                          * it reads clearly as "future / uncertain" against the
                          * solid teal flown path. Sits under the transmit dots
                          * and balloon pins. */}
                        {forecastGeoJSON && (
                            <Source id="v2-forecast-path" type="geojson" data={forecastGeoJSON}>
                                <Layer
                                    id="v2-forecast-line"
                                    type="line"
                                    paint={{
                                        'line-color': '#f59e0b',
                                        'line-opacity': 0.7,
                                        'line-dasharray': [2, 2],
                                        'line-width': [
                                            'interpolate', ['linear'], ['zoom'],
                                            3, 1.2,
                                            8, 1.8,
                                            14, 2.6,
                                        ],
                                    }}
                                />
                            </Source>
                        )}

                        {/* Transmitted-position dots — the raw points the balloon
                          * reported. Drawn on top of the flown-path line so each
                          * uplink reads as a distinct fix. */}
                        {showTransmitPoints && transmitPointsGeoJSON && (
                            <Source id="v2-transmit-points" type="geojson" data={transmitPointsGeoJSON}>
                                <Layer
                                    id="v2-transmit-point"
                                    type="circle"
                                    paint={{
                                        /* Hollow ringed nodes — a dark core with a
                                          * bright teal ring reads as a distinct
                                          * "reported here" marker against the solid
                                          * teal flown-path line. */
                                        'circle-color': '#0b1220',
                                        'circle-radius': [
                                            'interpolate', ['linear'], ['zoom'],
                                            3, 2.4,
                                            8, 3.4,
                                            14, 4.6,
                                        ],
                                        'circle-opacity': 1,
                                        'circle-stroke-width': 1.6,
                                        'circle-stroke-color': '#5eead4',
                                    }}
                                />
                            </Source>
                        )}

                        {/* Reception lines render BEHIND the balloon/gateway pins so
                          * the pins always sit on top. */}
                        {receptionLinesGeoJSON && (
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

                        {validGateways.length > 0 && (
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
        </div>
    );
}
