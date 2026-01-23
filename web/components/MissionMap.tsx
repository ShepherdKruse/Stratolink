'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { createClient as createSupabaseClient } from '@/lib/supabase';

interface MissionMapProps {
    projection?: 'globe' | 'mercator';
    onProjectionChange?: (projection: 'globe' | 'mercator') => void;
}

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
}

export default function MissionMap({ projection = 'globe', onProjectionChange }: MissionMapProps) {
    const [viewState, setViewState] = useState({
        longitude: -75,
        latitude: 40,
        zoom: 3,
        pitch: projection === 'globe' ? 45 : 0,
        bearing: 0,
    });

    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);

    // Fetch active balloons from Supabase
    useEffect(() => {
        async function fetchBalloons() {
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                return;
            }

            try {
                const supabase = createSupabaseClient();
                
                // Get active balloons (recent telemetry within last hour)
                const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                
                const { data, error } = await supabase
                    .from('telemetry')
                    .select('device_id, lat, lon, altitude_m, time')
                    .gte('time', oneHourAgo)
                    .gt('altitude_m', 100)
                    .order('time', { ascending: false });

                if (error) {
                    console.error('Error fetching balloons:', error);
                    return;
                }

                console.log('Fetched balloons from Supabase:', data);

                if (data && data.length > 0) {
                    // Get latest telemetry per device
                    const latestByDevice = new Map<string, BalloonData>();
                    data.forEach((row: any) => {
                        if (!latestByDevice.has(row.device_id)) {
                            latestByDevice.set(row.device_id, {
                                id: row.device_id,
                                lat: row.lat,
                                lon: row.lon,
                                altitude_m: row.altitude_m,
                            });
                        }
                    });
                    const balloons = Array.from(latestByDevice.values());
                    console.log('Processed balloons for map:', balloons);
                    setBalloonData(balloons);
                } else {
                    console.log('No active balloons found in last hour');
                    setBalloonData([]);
                }
            } catch (error) {
                console.error('Supabase fetch error:', error);
            }
        }

        fetchBalloons();
        // Refresh every 30 seconds
        const interval = setInterval(fetchBalloons, 30000);
        
        return () => clearInterval(interval);
    }, []);

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

    return (
        <div className="w-full h-full relative">
            <Map
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
            >
                {/* Balloon markers with 3D visualization */}
                <Source id="balloons" type="geojson" data={balloonGeoJSON}>
                    {/* Glowing cyan dots at balloon positions */}
                    <Layer
                        id="balloon-markers"
                        type="circle"
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
                    
                    {/* White circles representing ground connection points */}
                    <Layer
                        id="balloon-ground"
                        type="circle"
                        paint={{
                            'circle-color': '#ffffff',
                            'circle-radius': 3,
                            'circle-opacity': 0.4,
                        }}
                    />
                </Source>
            </Map>
        </div>
    );
}
