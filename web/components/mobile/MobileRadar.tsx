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
    selectedBalloonId?: string | null;
}

export default function MobileRadar({ balloonData, onBalloonClick, userLocation, selectedBalloonId }: MobileRadarProps) {
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

        // Skip device orientation in iframe context
        if (typeof window === 'undefined' || window.self !== window.top) {
            return;
        }

        if (typeof DeviceOrientationEvent !== 'undefined' && typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
            // iOS 13+ requires permission
            (DeviceOrientationEvent as any).requestPermission()
                .then((response: string) => {
                    if (response === 'granted' && typeof window !== 'undefined') {
                        window.addEventListener('deviceorientation', handleOrientation);
                    }
                })
                .catch(() => {
                    console.log('Compass permission denied');
                });
        } else if (typeof window !== 'undefined') {
            window.addEventListener('deviceorientation', handleOrientation);
        }

        return () => {
            if (typeof window !== 'undefined') {
                window.removeEventListener('deviceorientation', handleOrientation);
            }
        };
    }, [compassEnabled]);

    // Get user location
    useEffect(() => {
        // Skip geolocation in iframe context
        if (typeof window === 'undefined' || window.self !== window.top) {
            return;
        }
        
        if (typeof navigator !== 'undefined' && navigator.geolocation) {
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
                                ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                '#4a9',
                                ['>', ['get', 'altitude'], 100],
                                '#4a90d9',
                                '#666'
                            ],
                            'circle-radius': [
                                'case',
                                ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                12,
                                8
                            ],
                            'circle-opacity': 0.9,
                            'circle-stroke-width': [
                                'case',
                                ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                3,
                                2
                            ],
                            'circle-stroke-color': [
                                'case',
                                ['==', ['get', 'deviceId'], selectedBalloonId || ''],
                                '#4a9',
                                '#fff'
                            ],
                            'circle-stroke-opacity': 0.8,
                        }}
                    />
                </Source>
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
