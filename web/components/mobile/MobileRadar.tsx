'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { Compass } from 'lucide-react';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
}

interface MobileRadarProps {
    balloonData: BalloonData[];
    onBalloonClick: (balloonId: string) => void;
    userLocation?: { lat: number; lon: number } | null;
}

export default function MobileRadar({ balloonData, onBalloonClick, userLocation, selectedBalloonId, flightPathData = [], playbackTime }: MobileRadarProps) {
    const mapRef = useRef<MapRef>(null);
    const [mapBearing, setMapBearing] = useState(0);
    const [compassEnabled, setCompassEnabled] = useState(false);

    // Find nearest balloon
    const nearestBalloon = useCallback(() => {
        if (!userLocation || balloonData.length === 0) return null;

        let nearest: BalloonData | null = null;
        let minDistance = Infinity;

        balloonData.forEach(balloon => {
            const R = 6371; // Earth radius in km
            const dLat = (balloon.lat - userLocation.lat) * Math.PI / 180;
            const dLon = (balloon.lon - userLocation.lon) * Math.PI / 180;
            const a = 
                Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(userLocation.lat * Math.PI / 180) * Math.cos(balloon.lat * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            const distance = R * c;

            if (distance < minDistance) {
                minDistance = distance;
                nearest = balloon;
            }
        });

        return nearest ? { balloon: nearest, distance: minDistance * 0.621371 } : null; // Convert to miles
    }, [balloonData, userLocation]);

    const nearest = nearestBalloon();

    // Compass orientation using device orientation API
    useEffect(() => {
        if (!compassEnabled) return;

        const handleOrientation = (event: DeviceOrientationEvent) => {
            if (event.alpha !== null && mapRef.current) {
                // alpha is compass heading (0-360)
                const bearing = -event.alpha; // Negative for map rotation
                setMapBearing(bearing);
                mapRef.current.setBearing(bearing);
            }
        };

        if (typeof DeviceOrientationEvent !== 'undefined' && typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
            // iOS 13+ requires permission
            (DeviceOrientationEvent as any).requestPermission()
                .then((response: string) => {
                    if (response === 'granted') {
                        window.addEventListener('deviceorientation', handleOrientation);
                    }
                })
                .catch(() => {
                    console.log('Compass permission denied');
                });
        } else {
            window.addEventListener('deviceorientation', handleOrientation);
        }

        return () => {
            window.removeEventListener('deviceorientation', handleOrientation);
        };
    }, [compassEnabled]);

    // Get user location
    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    // Store in state or context if needed
                },
                () => {
                    console.log('Geolocation denied');
                }
            );
        }
    }, []);

    const balloonGeoJSON = {
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

    // Create flight path GeoJSON if balloon is selected
    const flightPathGeoJSON = flightPathData.length > 0 && selectedBalloonId ? {
        type: 'FeatureCollection' as const,
        features: [{
            type: 'Feature' as const,
            geometry: {
                type: 'LineString' as const,
                coordinates: flightPathData
                    .filter(point => {
                        if (!playbackTime) return true;
                        const pointTime = point.time instanceof Date ? point.time : new Date(point.time);
                        return pointTime <= playbackTime;
                    })
                    .map(point => [point.lon, point.lat]),
            },
        }],
    } : null;

    const handleMarkerClick = useCallback((e: any) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const balloonId = feature.properties?.deviceId;
        if (balloonId) {
            onBalloonClick(balloonId);
        }
    }, [onBalloonClick]);

    return (
        <div className="relative w-full h-full">
            {/* Map - 2D Default for Mobile */}
            <Map
                ref={mapRef}
                mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
                initialViewState={{
                    longitude: userLocation?.lon ?? -75,
                    latitude: userLocation?.lat ?? 40,
                    zoom: 3,
                    pitch: 0,
                    bearing: mapBearing,
                }}
                style={{ width: '100%', height: '100%' }}
                mapStyle="mapbox://styles/mapbox/standard"
                projection="mercator"
                interactiveLayerIds={['balloon-markers']}
                onClick={handleMarkerClick}
                cursor="pointer"
            >
                {/* Balloon Markers */}
                <Source id="balloons" type="geojson" data={balloonGeoJSON}>
                    <Layer
                        id="balloon-markers"
                        type="circle"
                        paint={{
                            'circle-color': [
                                'case',
                                ['>', ['get', 'altitude'], 100],
                                '#4a90d9',
                                '#666'
                            ],
                            'circle-radius': 8,
                            'circle-opacity': 0.9,
                            'circle-stroke-width': 2,
                            'circle-stroke-color': '#fff',
                            'circle-stroke-opacity': 0.8,
                        }}
                    />
                </Source>

                {/* Flight Path Line - Only show if balloon is selected */}
                {flightPathGeoJSON && (
                    <Source id="flight-path" type="geojson" data={flightPathGeoJSON} lineMetrics={true}>
                        <Layer
                            id="flight-path-line"
                            type="line"
                            paint={{
                                'line-width': 3,
                                'line-opacity': 0.8,
                                'line-gradient': [
                                    'interpolate',
                                    ['linear'],
                                    ['line-progress'],
                                    0, '#4a90d9',
                                    1, 'rgba(74, 144, 217, 0)'
                                ],
                            }}
                        />
                    </Source>
                )}
            </Map>

            {/* Nearby Pill - Top Center */}
            {nearest && (
                <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-20">
                    <div className="bg-[#1a1a1a]/95 backdrop-blur-md border border-[#333] px-4 py-2 rounded-full">
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] text-[#666] font-mono">Nearest:</span>
                            <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">{nearest.balloon.id}</span>
                            <span className="text-[10px] text-[#e5e5e5] font-mono">
                                ({nearest.distance.toFixed(0)} mi ↑)
                            </span>
                        </div>
                    </div>
                </div>
            )}

            {/* Compass Button - Bottom Right */}
            <button
                onClick={() => setCompassEnabled(!compassEnabled)}
                className={`absolute bottom-20 right-4 z-20 w-14 h-14 rounded-full flex items-center justify-center border transition-all min-h-[44px] min-w-[44px] ${
                    compassEnabled
                        ? 'bg-[#4a90d9] border-[#4a90d9] text-white'
                        : 'bg-[#1a1a1a]/95 backdrop-blur-md border-[#333] text-[#666]'
                }`}
            >
                <Compass size={24} />
            </button>
        </div>
    );
}
