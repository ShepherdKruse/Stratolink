'use client';

import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';

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
}

export default function MissionMap({ 
    projection = 'globe', 
    onProjectionChange, 
    balloonData = [],
    activeBalloonId = null,
    onActiveBalloonChange,
    flightPathData = [],
    playbackTime = null
}: MissionMapProps) {
    const mapRef = useRef<MapRef>(null);
    const [viewState, setViewState] = useState({
        longitude: -75,
        latitude: 40,
        zoom: 3,
        pitch: projection === 'globe' ? 45 : 0,
        bearing: 0,
    });

    // Enter Ride Along mode
    const enterRideAlongMode = useCallback((balloon: BalloonData) => {
        if (!mapRef.current) return;
        
        const bearing = balloon.velocity_heading ?? 90;
        
        mapRef.current.flyTo({
            center: [balloon.lon, balloon.lat],
            zoom: 12,
            pitch: 75,
            bearing: bearing,
            duration: 2000,
        });
        
        if (onActiveBalloonChange) {
            onActiveBalloonChange(balloon.id);
        }
    }, [onActiveBalloonChange]);

    // Reset camera when exiting Ride Along mode
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

    // Handle marker click
    const handleMarkerClick = useCallback((e: any) => {
        const feature = e.features?.[0];
        if (!feature) return;
        
        const balloonId = feature.properties?.deviceId;
        const balloon = balloonData.find(b => b.id === balloonId);
        
        if (balloon) {
            enterRideAlongMode(balloon);
        }
    }, [balloonData, enterRideAlongMode]);


    // Adjust view state when projection changes
    const handleViewStateChange = useCallback((evt: any) => {
        setViewState(evt.viewState);
    }, []);

    // Reset pitch when switching to 2D
    const adjustedViewState = useMemo(() => {
        if (projection === 'mercator') {
            return { ...viewState, pitch: 0, bearing: 0 };
        }
        return viewState;
    }, [viewState, projection]);

    // Create GeoJSON for balloon positions (markers at altitude)
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

    // Create GeoJSON for active balloon 3D model
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

    // Create GeoJSON for flight path with lineMetrics for gradient
    const flightPathGeoJSON = useMemo(() => {
        if (!activeBalloonId || !flightPathData || flightPathData.length < 2) {
            if (activeBalloonId && flightPathData.length < 2) {
                console.warn('⚠️ Not enough flight path points:', flightPathData.length);
            }
            return null;
        }
        
        // Filter path points up to playbackTime if specified
        let pathPoints = flightPathData;
        if (playbackTime) {
            const playbackTimestamp = playbackTime.getTime();
            pathPoints = flightPathData.filter(point => {
                const pointTime = point.time instanceof Date ? point.time.getTime() : new Date(point.time).getTime();
                return pointTime <= playbackTimestamp;
            });
        }
        
        if (pathPoints.length < 2) {
            console.warn('⚠️ Filtered path has less than 2 points:', pathPoints.length);
            return null;
        }
        
        const coordinates = pathPoints.map(point => {
            if (typeof point.lat !== 'number' || typeof point.lon !== 'number') {
                console.error('❌ Invalid coordinate:', point);
                return null;
            }
            return [point.lon, point.lat] as [number, number];
        }).filter((coord): coord is [number, number] => coord !== null);
        
        if (coordinates.length < 2) {
            console.error('❌ Not enough valid coordinates:', coordinates.length);
            return null;
        }
        
        const geoJSON = {
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
        
        // Debug log
        console.log('🛤️ Flight path GeoJSON created:', {
            activeBalloonId,
            pathPoints: pathPoints.length,
            totalPoints: flightPathData.length,
            playbackTime: playbackTime ? playbackTime.toISOString() : 'null',
            coordinates: coordinates.length,
            firstCoord: coordinates[0],
            lastCoord: coordinates[coordinates.length - 1]
        });
        
        return geoJSON;
    }, [activeBalloonId, flightPathData, playbackTime]);

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
                fog={projection === 'globe' ? {
                    color: 'rgb(4, 7, 37)',
                    'high-color': 'rgb(0, 0, 0)',
                    'horizon-blend': 0.02,
                    'space-color': 'rgb(0, 0, 0)',
                    'star-intensity': 0.6,
                } : undefined}
                terrain={projection === 'globe' ? { source: 'mapbox-dem', exaggeration: 1.5 } : undefined}
                interactiveLayerIds={['balloon-markers-active', 'balloon-markers-landed']}
                onClick={handleMarkerClick}
                cursor="pointer"
            >
                {/* Balloon markers with 3D visualization */}
                <Source id="balloons" type="geojson" data={balloonGeoJSON}>
                    {/* Glowing cyan dots for active balloons (altitude > 100m) */}
                    <Layer
                        id="balloon-markers-active"
                        type="circle"
                        filter={['>', ['get', 'altitude'], 100]}
                        paint={{
                            'circle-color': '#00ffff',
                            'circle-radius': [
                                'interpolate',
                                ['linear'],
                                ['get', 'altitude'],
                                0, 6,
                                20000, 12
                            ],
                            'circle-opacity': 0.9,
                            'circle-stroke-width': 2,
                            'circle-stroke-color': '#00ffff',
                            'circle-stroke-opacity': 0.5,
                            'circle-blur': 0.5,
                        }}
                    />
                    
                    {/* Gray dots for landed/inactive balloons (altitude <= 100m) */}
                    <Layer
                        id="balloon-markers-landed"
                        type="circle"
                        filter={['<=', ['get', 'altitude'], 100]}
                        paint={{
                            'circle-color': '#888888',
                            'circle-radius': 8,
                            'circle-opacity': 0.8,
                            'circle-stroke-width': 2,
                            'circle-stroke-color': '#aaaaaa',
                            'circle-stroke-opacity': 0.6,
                        }}
                    />
                </Source>

                {/* Flight Path Trail for Active Balloon */}
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
                                    3, 2,
                                    12, 4,
                                    15, 6
                                ],
                                'line-blur': 2,
                                'line-opacity': 0.9,
                                'line-gradient': [
                                    'interpolate',
                                    ['linear'],
                                    ['line-progress'],
                                    0, 'rgba(255, 255, 255, 1)',      // White at head (most recent)
                                    0.3, 'rgba(0, 255, 255, 0.9)',    // Cyan
                                    0.7, 'rgba(0, 255, 255, 0.6)',    // Fading cyan
                                    1, 'rgba(0, 255, 255, 0)'         // Transparent at tail (oldest)
                                ],
                            }}
                        />
                    </Source>
                )}

                {/* 3D Model for Active Balloon */}
                {activeBalloonGeoJSON && (
                    <Source id="active-balloon" type="geojson" data={activeBalloonGeoJSON}>
                        {/* 3D Sphere representation using circle layer with elevation */}
                        <Layer
                            id="active-balloon-3d"
                            type="circle"
                            paint={{
                                'circle-color': '#00ff00',
                                'circle-radius': 20,
                                'circle-opacity': 0.8,
                                'circle-stroke-width': 3,
                                'circle-stroke-color': '#00ff00',
                                'circle-stroke-opacity': 1,
                                'circle-blur': 1,
                            }}
                        />
                        {/* Glow effect */}
                        <Layer
                            id="active-balloon-glow"
                            type="circle"
                            paint={{
                                'circle-color': '#00ff00',
                                'circle-radius': 30,
                                'circle-opacity': 0.3,
                                'circle-blur': 2,
                            }}
                        />
                    </Source>
                )}
            </Map>
        </div>
    );
}
