'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import GatewayLayer from '@/components/maps/GatewayLayer';
import GatewayLegend from '@/components/maps/GatewayLegend';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';

import { isUsableGpsCoordinate } from '@/lib/mapGeo';

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

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
    velocity_heading?: number;
    battery_voltage?: number;
}

interface FlightPathPoint {
    lat: number;
    lon: number;
    time: Date | string;
}

interface MissionMapProps {
    projection?: 'globe' | 'mercator';
    onProjectionChange?: (projection: 'globe' | 'mercator') => void;
    balloonData?: BalloonData[];
    activeBalloonId?: string | null;
    onActiveBalloonChange?: (balloonId: string | null) => void;
    flightPathData?: FlightPathPoint[];
    playbackTime?: Date | null;
    isSidebarOpen?: boolean;
}

export default function MissionMap({ 
    projection = 'globe', 
    onProjectionChange, 
    balloonData = [],
    activeBalloonId = null,
    onActiveBalloonChange,
    flightPathData = [],
    playbackTime = null,
    isSidebarOpen = false
}: MissionMapProps) {
    const mapRef = useRef<MapRef>(null);
    const [viewState, setViewState] = useState({
        longitude: -75,
        latitude: 40,
        zoom: 3,
        pitch: projection === 'globe' ? 45 : 0,
        bearing: 0,
    });

    /* Track when the Mapbox style is fully loaded. Sources/Layers must not
     * mount before the style is ready or mapbox-gl throws
     * "Style is not done loading" and the ErrorBoundary kicks in, blanking
     * the whole map. */
    const [styleLoaded, setStyleLoaded] = useState(false);

    const handleStyleLoad = useCallback(() => {
        setStyleLoaded(true);
        const map = mapRef.current?.getMap();
        if (map) quietBasemapLabels(map);
    }, []);

    /* If the underlying style changes (projection toggle remounts the Map
     * via `key={projection}`), reset the flag so we don't render layers
     * against a stale style instance. */
    useEffect(() => {
        setStyleLoaded(false);
    }, [projection]);

    const [isMobile, setIsMobile] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);

    useEffect(() => {
        setWebglOk(isWebGLAvailable());
    }, []);

    useEffect(() => {
        const checkMobile = () => {
            setIsMobile(window.innerWidth < 768);
        };
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);

    const enterRideAlongMode = useCallback((balloon: BalloonData) => {
        if (!mapRef.current) return;
        
        const bearing = balloon.velocity_heading ?? 90;
        // Mobile: zoom 10 (wider field of view), Desktop: zoom 12 (closer)
        const zoom = isMobile ? 10 : 12;
        
        mapRef.current.flyTo({
            center: [balloon.lon, balloon.lat],
            zoom: zoom,
            pitch: 75,
            bearing: bearing,
            duration: 2000,
        });
        
        if (onActiveBalloonChange) {
            onActiveBalloonChange(balloon.id);
        }
    }, [onActiveBalloonChange, isMobile]);

    useEffect(() => {
        if (!activeBalloonId && mapRef.current) {
            mapRef.current.flyTo({
                center: [-75, 40],
                zoom: 3,
                pitch: projection === 'globe' ? 45 : 0,
                bearing: 0,
                duration: 2000,
            });
        }
    }, [activeBalloonId, projection]);

    const handleMarkerClick = useCallback((e: any) => {
        const feature = e.features?.[0];
        if (!feature) return;
        
        const balloonId = feature.properties?.deviceId;
        const balloon = balloonData.find(b => b.id === balloonId);
        
        if (balloon) {
            enterRideAlongMode(balloon);
        }
    }, [balloonData, enterRideAlongMode]);

    const handleViewStateChange = useCallback((evt: any) => {
        setViewState(evt.viewState);
    }, []);

    const adjustedViewState = useMemo(() => {
        if (projection === 'mercator') {
            return { ...viewState, pitch: 0, bearing: 0 };
        }
        return viewState;
    }, [viewState, projection]);

    const balloonGeoJSON = useMemo(() => {
        return {
            type: 'FeatureCollection' as const,
            features: balloonData.map((balloon) => ({
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
        };
    }, [balloonData]);

    const activeBalloonGeoJSON = useMemo(() => {
        if (!activeBalloonId) return null;
        
        const balloon = balloonData.find(b => b.id === activeBalloonId);
        if (!balloon) return null;
        
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                id: `active-${balloon.id}`,
                geometry: {
                    type: 'Point' as const,
                    coordinates: [balloon.lon, balloon.lat],
                },
                properties: {
                    altitude: balloon.altitude_m,
                    deviceId: balloon.id,
                },
            }],
        };
    }, [activeBalloonId, balloonData]);

    const flightPathGeoJSON = useMemo(() => {
        if (!activeBalloonId || !flightPathData || flightPathData.length < 2) {
            return null;
        }
        
        let pathPoints = flightPathData;
        if (playbackTime) {
            const playbackTimestamp = playbackTime.getTime();
            pathPoints = flightPathData.filter(point => {
                const pointTime = point.time instanceof Date ? point.time.getTime() : new Date(point.time).getTime();
                return pointTime <= playbackTimestamp;
            });
        }
        
        if (pathPoints.length < 2) {
            return null;
        }
        
        const coordinates = pathPoints
            .map((point) => {
                if (!isUsableGpsCoordinate(point.lat, point.lon)) {
                    return null;
                }
                return [point.lon, point.lat] as [number, number];
            })
            .filter((coord): coord is [number, number] => coord !== null);
        
        if (coordinates.length < 2) {
            return null;
        }
        
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                geometry: {
                    type: 'LineString' as const,
                    coordinates: coordinates,
                },
                properties: {},
            }],
        };
    }, [activeBalloonId, flightPathData, playbackTime]);

    // Calculate padding for mobile when sidebar is open
    const mapPadding = useMemo(() => {
        if (isMobile && isSidebarOpen && activeBalloonId) {
            // Push map center up so balloon is visible above bottom sheet
            return { bottom: 300, top: 0, left: 0, right: 0 };
        }
        return undefined;
    }, [isMobile, isSidebarOpen, activeBalloonId]);

    /* If the browser cannot create a WebGL context (hardware acceleration
     * disabled, GPU blocklisted, locked-down sandbox) Mapbox would throw on
     * mount and the ErrorBoundary above would blank the whole dashboard.
     * Render a graceful placeholder with self-help guidance instead. */
    if (webglOk === false) {
        return (
            <div className="w-full h-full relative flex items-center justify-center bg-[#0a0a0a]">
                <div className="max-w-md text-center px-6 font-mono text-xs text-[#bbb]">
                    <div className="text-[#ff6b6b] text-sm mb-3 uppercase tracking-wider">Map unavailable</div>
                    <div className="text-[#aaa] mb-4">
                        Your browser can&apos;t create a WebGL context, so Mapbox can&apos;t render the globe.
                    </div>
                    <div className="text-[#888] text-[11px] leading-relaxed text-left bg-[#141414] border border-[#333] p-3 rounded">
                        <div className="text-[#ccc] mb-2">Try one of these:</div>
                        <div>1. Chrome/Edge: <code className="text-[#9ecbff]">chrome://settings/system</code> &rarr; enable &ldquo;Use graphics acceleration when available&rdquo; &rarr; restart browser.</div>
                        <div className="mt-2">2. Check <code className="text-[#9ecbff]">chrome://gpu</code> &mdash; WebGL should say &ldquo;Hardware accelerated&rdquo;.</div>
                        <div className="mt-2">3. Test at <a href="https://get.webgl.org" target="_blank" rel="noreferrer" className="text-[#9ecbff] underline">get.webgl.org</a> to confirm the browser config.</div>
                    </div>
                </div>
            </div>
        );
    }

    if (webglOk === null) {
        return <div className="w-full h-full bg-[#0a0a0a]" />;
    }

    return (
        <div className="w-full h-full relative">
            <Map
                ref={mapRef}
                key={projection}
                {...adjustedViewState}
                onMove={handleViewStateChange}
                mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
                style={{ width: '100%', height: '100%' }}
                mapStyle="mapbox://styles/mapbox/dark-v11"
                projection={projection === 'globe' ? 'globe' : 'mercator'}
                padding={mapPadding}
                fog={projection === 'globe' ? {
                    color: 'rgb(20, 20, 20)',
                    'high-color': 'rgb(10, 10, 10)',
                    'horizon-blend': 0.02,
                    'space-color': 'rgb(5, 5, 5)',
                    'star-intensity': 0.4,
                } : undefined}
                interactiveLayerIds={['balloon-markers-active', 'balloon-markers-landed']}
                onClick={handleMarkerClick}
                onLoad={handleStyleLoad}
                onStyleData={handleStyleLoad}
                cursor="pointer"
            >
                {styleLoaded && (
                    <>
                {/* Static TTN gateway coverage — at the bottom so it
                  * sits under the balloon markers and tracks. */}
                <GatewayLayer />

                {/* Balloon markers - functional colors from palette */}
                <Source id="balloons" type="geojson" data={balloonGeoJSON}>
                    {/* Active balloons - accent blue */}
                    <Layer
                        id="balloon-markers-active"
                        type="circle"
                        filter={['>', ['get', 'altitude'], 100]}
                        paint={{
                            'circle-color': '#4a90d9',
                            'circle-radius': [
                                'interpolate',
                                ['linear'],
                                ['get', 'altitude'],
                                0, 5,
                                20000, 8
                            ],
                            'circle-opacity': 0.9,
                            'circle-stroke-width': 1,
                            'circle-stroke-color': '#6ba3e0',
                            'circle-stroke-opacity': 0.7,
                        }}
                    />
                    
                    {/* Landed balloons - tertiary gray */}
                    <Layer
                        id="balloon-markers-landed"
                        type="circle"
                        filter={['<=', ['get', 'altitude'], 100]}
                        paint={{
                            'circle-color': '#666',
                            'circle-radius': 5,
                            'circle-opacity': 0.7,
                            'circle-stroke-width': 1,
                            'circle-stroke-color': '#999',
                            'circle-stroke-opacity': 0.5,
                        }}
                    />
                </Source>

                {/* Flight Path Trail - accent blue with fade */}
                {flightPathGeoJSON && flightPathGeoJSON.features[0]?.geometry.coordinates.length >= 2 && (
                    <Source 
                        key={`flight-path-${activeBalloonId}-${playbackTime?.getTime() || 'full'}`}
                        id="flight-path" 
                        type="geojson" 
                        data={flightPathGeoJSON}
                        lineMetrics={true}
                    >
                        <Layer
                            id="flight-path-line"
                            type="line"
                            paint={{
                                'line-width': [
                                    'interpolate',
                                    ['linear'],
                                    ['zoom'],
                                    3, 1.5,
                                    12, 3,
                                    15, 4
                                ],
                                'line-opacity': 0.8,
                                'line-gradient': [
                                    'interpolate',
                                    ['linear'],
                                    ['line-progress'],
                                    0, 'rgba(74, 144, 217, 0)',
                                    0.7, 'rgba(74, 144, 217, 0.6)',
                                    1, 'rgba(74, 144, 217, 1)'
                                ],
                            }}
                        />
                    </Source>
                )}

                {/* Active Balloon Marker - highlighted */}
                {activeBalloonGeoJSON && (
                    <Source id="active-balloon" type="geojson" data={activeBalloonGeoJSON}>
                        <Layer
                            id="active-balloon-marker"
                            type="circle"
                            paint={{
                                'circle-color': '#4a9',
                                'circle-radius': 8,
                                'circle-opacity': 0.9,
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#4a9',
                                'circle-stroke-opacity': 0.5,
                            }}
                        />
                    </Source>
                )}
                    </>
                )}
            </Map>
            <GatewayLegend />
        </div>
    );
}
