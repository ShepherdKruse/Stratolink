'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { Compass } from 'lucide-react';
import { isUsableGpsCoordinate, isValidWgs84Point, isWebGLAvailable } from '@/lib/mapGeo';
import mapboxgl from 'mapbox-gl';
import type { MapMouseEvent } from 'mapbox-gl';
import type { GatewayReception } from '../dashboard-v2/atoms';
import MobileGatewayMapLayers from './MobileGatewayMapLayers';
import { gatewaysWithLocation } from './mobileGatewayGeo';
import GatewayLayer from '@/components/maps/GatewayLayer';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
}

interface FlightPathPoint {
    lat: number;
    lon: number;
    time?: Date;
}

interface MobileRadarProps {
    balloonData: BalloonData[];
    onBalloonClick: (balloonId: string) => void;
    userLocation?: { lat: number; lon: number } | null;
    selectedBalloonId?: string | null;
    flightPathData?: FlightPathPoint[];
    gateways?: GatewayReception[] | null;
}

const MAP_STYLE_DARK = 'mapbox://styles/mapbox/dark-v11';

function buildLngLatBounds(coords: ReadonlyArray<readonly [number, number]>): mapboxgl.LngLatBounds | null {
    if (!coords.length) return null;
    const first = coords[0] as mapboxgl.LngLatLike;
    const b = new mapboxgl.LngLatBounds(first, first);
    for (let i = 1; i < coords.length; i++) {
        b.extend(coords[i] as mapboxgl.LngLatLike);
    }
    return b;
}

export default function MobileRadar({
    balloonData,
    onBalloonClick,
    userLocation,
    selectedBalloonId,
    flightPathData = [],
    gateways = null,
}: MobileRadarProps) {
    const mapRef = useRef<MapRef>(null);
    const [mapBearing, setMapBearing] = useState(0);
    const [compassEnabled, setCompassEnabled] = useState(false);
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);
    const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

    useEffect(() => {
        setWebglOk(isWebGLAvailable());
    }, []);

    const handleStyleLoad = useCallback(() => {
        setStyleLoaded(true);
        const map = mapRef.current?.getMap();
        if (map) quietBasemapLabels(map);
    }, []);

    const mapBalloons = useMemo(
        () => balloonData.filter((b) => isUsableGpsCoordinate(b.lat, b.lon)),
        [balloonData],
    );

    const nearestBalloon = useCallback((): { balloon: BalloonData; distance: number } | null => {
        if (!userLocation || mapBalloons.length === 0) return null;

        let nearest: BalloonData | null = null;
        let minDistance = Infinity;

        mapBalloons.forEach((balloon) => {
            const R = 6371;
            const dLat = ((balloon.lat - userLocation.lat) * Math.PI) / 180;
            const dLon = ((balloon.lon - userLocation.lon) * Math.PI) / 180;
            const a =
                Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos((userLocation.lat * Math.PI) / 180) *
                    Math.cos((balloon.lat * Math.PI) / 180) *
                    Math.sin(dLon / 2) *
                    Math.sin(dLon / 2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            const distance = R * c;

            if (distance < minDistance) {
                minDistance = distance;
                nearest = balloon;
            }
        });

        return nearest ? { balloon: nearest, distance: minDistance * 0.621371 } : null;
    }, [mapBalloons, userLocation]);

    const nearest = nearestBalloon();

    const selectedBalloon = selectedBalloonId
        ? mapBalloons.find((b) => b.id === selectedBalloonId)
        : undefined;
    const gatewayBalloonLat = selectedBalloon?.lat ?? null;
    const gatewayBalloonLon = selectedBalloon?.lon ?? null;
    const locatedGatewayCount = gatewaysWithLocation(gateways).length;

    const balloonGeoJSON = useMemo(
        () =>
            ({
                type: 'FeatureCollection' as const,
                features: mapBalloons.map((balloon) => ({
                    type: 'Feature' as const,
                    id: balloon.id,
                    geometry: {
                        type: 'Point' as const,
                        coordinates: [balloon.lon, balloon.lat],
                    },
                    properties: {
                        altitude: balloon.altitude_m,
                        deviceId: balloon.id,
                    },
                })),
            }) as GeoJSON.FeatureCollection,
        [mapBalloons],
    );

    const flightLineGeoJSON = useMemo(() => {
        const pathCoords = flightPathData
            .filter((p) => isUsableGpsCoordinate(p.lat, p.lon))
            .map((p) => [p.lon, p.lat] as [number, number]);
        if (!selectedBalloonId || pathCoords.length < 2) {
            return { type: 'FeatureCollection' as const, features: [] as GeoJSON.Feature[] };
        }
        return {
            type: 'FeatureCollection' as const,
            features: [
                {
                    type: 'Feature' as const,
                    geometry: {
                        type: 'LineString' as const,
                        coordinates: pathCoords,
                    },
                    properties: {},
                },
            ],
        } satisfies GeoJSON.FeatureCollection;
    }, [flightPathData, selectedBalloonId]);

    const lastSelectionRef = useRef<string | null>(null);
    const lastFleetFitAtRef = useRef(0);
    const flightPathFitKeyRef = useRef('');

    useEffect(() => {
        if (!styleLoaded || !mapRef.current || !webglOk) return;
        const map = mapRef.current.getMap();
        if (!map?.loaded?.()) return;

        const pathFitKey = `${selectedBalloonId ?? ''}:${flightLineGeoJSON.features.length}`;
        if (flightPathFitKeyRef.current !== pathFitKey) {
            flightPathFitKeyRef.current = pathFitKey;
            lastFleetFitAtRef.current = 0;
        }

        const lngLatsFromBalloons = mapBalloons.map((b): [number, number] => [b.lon, b.lat]);

        let bounds: mapboxgl.LngLatBounds | null = null;

        const pathCoords =
            selectedBalloonId && flightLineGeoJSON.features[0]?.geometry?.type === 'LineString'
                ? (flightLineGeoJSON.features[0].geometry as GeoJSON.LineString).coordinates.map(
                      (c): [number, number] => [Number(c[0]), Number(c[1])],
                  )
                : [];
        bounds = pathCoords.length >= 2 ? buildLngLatBounds(pathCoords) : null;

        const gatewayPts = gatewaysWithLocation(gateways).map(
            (g): [number, number] => [g.lon!, g.lat!],
        );
        if (gatewayPts.length) {
            const gwBounds = buildLngLatBounds(gatewayPts);
            if (gwBounds && !gwBounds.isEmpty()) {
                if (bounds && !bounds.isEmpty()) {
                    for (const pt of gatewayPts) bounds.extend(pt);
                } else {
                    bounds = gwBounds;
                }
            }
        }

        if (!bounds || bounds.isEmpty()) {
            bounds = lngLatsFromBalloons.length > 0 ? buildLngLatBounds(lngLatsFromBalloons) : null;
        }

        const selectionChanged = (selectedBalloonId ?? null) !== lastSelectionRef.current;
        lastSelectionRef.current = selectedBalloonId ?? null;

        const now = Date.now();
        const throttleMs = 8000;
        const allowFleetRefit =
            selectionChanged ||
            lngLatsFromBalloons.length === 0 ||
            now - lastFleetFitAtRef.current > throttleMs;

        if (!allowFleetRefit) return;

        if (bounds && !bounds.isEmpty()) {
            try {
                map.fitBounds(bounds, {
                    padding: { top: 80, bottom: 120, left: 24, right: 24 },
                    maxZoom: 12,
                    duration: selectionChanged ? 900 : 1200,
                });
                lastFleetFitAtRef.current = now;
                return;
            } catch {
                /* ignore invalid bounds edge cases */
            }
        }

        if (lngLatsFromBalloons.length === 1 && isUsableGpsCoordinate(mapBalloons[0].lat, mapBalloons[0].lon)) {
            map.flyTo({
                center: [mapBalloons[0].lon, mapBalloons[0].lat],
                zoom: 8,
                duration: selectionChanged ? 900 : 1200,
            });
            lastFleetFitAtRef.current = now;
        }
    }, [mapBalloons, styleLoaded, flightLineGeoJSON, selectedBalloonId, webglOk, gateways]);

    useEffect(() => {
        if (!compassEnabled) return;

        const handleOrientation = (event: DeviceOrientationEvent) => {
            if (event.alpha !== null && mapRef.current) {
                const bearing = -event.alpha;
                setMapBearing(bearing);
                mapRef.current.setBearing(bearing);
            }
        };

        if (typeof window === 'undefined' || window.self !== window.top) {
            return;
        }

        if (
            typeof DeviceOrientationEvent !== 'undefined' &&
            typeof (DeviceOrientationEvent as typeof DeviceOrientationEvent & { requestPermission?: () => Promise<string> }).requestPermission === 'function'
        ) {
            (DeviceOrientationEvent as typeof DeviceOrientationEvent & { requestPermission: () => Promise<string> }).requestPermission()
                .then((response: string) => {
                    if (response === 'granted' && typeof window !== 'undefined') {
                        window.addEventListener('deviceorientation', handleOrientation);
                    }
                })
                .catch(() => {});
        } else if (typeof window !== 'undefined') {
            window.addEventListener('deviceorientation', handleOrientation);
        }

        return () => {
            if (typeof window !== 'undefined') {
                window.removeEventListener('deviceorientation', handleOrientation);
            }
        };
    }, [compassEnabled]);

    const handleMarkerClick = useCallback(
        (e: MapMouseEvent) => {
            const feature = e.features?.[0];
            const props = feature?.properties as Record<string, unknown> | null | undefined;
            const raw = props?.deviceId;
            const balloonId =
                typeof raw === 'string'
                    ? raw
                    : raw != null
                      ? String(raw)
                      : feature?.id != null
                        ? String(feature.id)
                        : null;
            if (balloonId) onBalloonClick(balloonId);
        },
        [onBalloonClick],
    );

    if (!mapboxToken) {
        return (
            <div className="flex h-full w-full items-center justify-center bg-[#1a1a1a] p-6 text-center">
                <p className="font-mono text-[12px] text-[#999]">
                    Map is unavailable—set NEXT_PUBLIC_MAPBOX_TOKEN to show the radar.
                </p>
            </div>
        );
    }

    if (webglOk === false) {
        return (
            <div className="flex h-full w-full items-center justify-center bg-[#1a1a1a] p-6 text-center">
                <p className="font-mono text-[12px] text-[#999]">WebGL is required for Mapbox maps. Enable WebGL or try another browser.</p>
            </div>
        );
    }

    return (
        <div className="relative h-full w-full">
            <Map
                ref={mapRef}
                mapboxAccessToken={mapboxToken}
                initialViewState={{
                    longitude: userLocation && isValidWgs84Point(userLocation.lat, userLocation.lon) ? userLocation.lon : -75,
                    latitude: userLocation && isValidWgs84Point(userLocation.lat, userLocation.lon) ? userLocation.lat : 40,
                    zoom: 3,
                    pitch: 0,
                    bearing: mapBearing,
                }}
                style={{ width: '100%', height: '100%' }}
                mapStyle={MAP_STYLE_DARK}
                projection="globe"
                interactiveLayerIds={['balloon-markers']}
                onClick={handleMarkerClick}
                onLoad={handleStyleLoad}
                onStyleData={(e: { dataType?: string }) => {
                    if (e?.dataType === 'style') handleStyleLoad();
                }}
                cursor="pointer">
                {/* Static TTN ground-station coverage — under the
                  * uplink-heard gateways + flight path. */}
                {styleLoaded && <GatewayLayer />}
                <MobileGatewayMapLayers
                    idPrefix="radar"
                    gateways={selectedBalloonId ? gateways : null}
                    balloonLat={gatewayBalloonLat}
                    balloonLon={gatewayBalloonLon}
                    styleLoaded={styleLoaded}
                />
                {styleLoaded && flightLineGeoJSON.features.length > 0 && (
                    <Source id="flight-path-mobile" type="geojson" data={flightLineGeoJSON}>
                        <Layer
                            id="flight-path-line-mobile"
                            type="line"
                            paint={{
                                'line-color': '#4a90d9',
                                'line-width': 4,
                                'line-opacity': 0.85,
                            }}
                            layout={{
                                'line-cap': 'round',
                                'line-join': 'round',
                            }}
                        />
                    </Source>
                )}
                {styleLoaded && (
                    <Source id="balloons" type="geojson" data={balloonGeoJSON}>
                        <Layer
                            id="balloon-markers"
                            type="circle"
                            paint={{
                                'circle-color': [
                                    'case',
                                    ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                    '#44aa99',
                                    ['>', ['get', 'altitude'], 100],
                                    '#4a90d9',
                                    '#888',
                                ],
                                'circle-radius': ['case', ['==', ['get', 'deviceId'], selectedBalloonId || ''], 12, 8],
                                'circle-opacity': 0.9,
                                'circle-stroke-width': ['case', ['==', ['get', 'deviceId'], selectedBalloonId || ''], 3, 2],
                                'circle-stroke-color': [
                                    'case',
                                    ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                    '#66ccbb',
                                    '#fff',
                                ],
                                'circle-stroke-opacity': 0.85,
                            }}
                        />
                    </Source>
                )}
            </Map>

            {selectedBalloonId && locatedGatewayCount > 0 ? (
                <div
                    className="absolute right-4 z-20 font-mono text-[10px] uppercase tracking-[0.08em]"
                    style={{
                        top: 'max(56px, calc(env(safe-area-inset-top) + 12px))',
                        padding: '4px 8px',
                        background: 'rgba(11, 14, 19, 0.82)',
                        border: '1px solid rgba(245, 158, 11, 0.45)',
                        color: '#fbbf24',
                        backdropFilter: 'blur(12px)',
                    }}>
                    {locatedGatewayCount} GW
                </div>
            ) : null}

            {nearest && (
                <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 transform">
                    <div className="rounded-full border border-[#333] bg-[#1a1a1a]/95 px-4 py-2 backdrop-blur-md">
                        <div className="flex items-center gap-2">
                            <span className="font-mono text-[10px] text-[#666]">Nearest:</span>
                            <span className="font-mono text-[12px] font-semibold text-[#4a90d9]">{nearest.balloon.id}</span>
                            <span className="font-mono text-[10px] text-[#e5e5e5]">({nearest.distance.toFixed(0)} mi ↑)</span>
                        </div>
                    </div>
                </div>
            )}

            <button
                type="button"
                onClick={() => setCompassEnabled(!compassEnabled)}
                className={`absolute bottom-20 right-4 z-20 flex h-14 w-14 min-h-[44px] min-w-[44px] items-center justify-center rounded-full border transition-all ${
                    compassEnabled
                        ? 'border-[#4a90d9] bg-[#4a90d9] text-white'
                        : 'border-[#333] bg-[#1a1a1a]/95 text-[#666] backdrop-blur-md'
                }`}>
                <Compass size={24} />
            </button>
        </div>
    );
}
