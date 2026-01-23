'use client';

import { useState, useEffect } from 'react';
import MissionMap from '@/components/MissionMap';
import { createClient } from '@/lib/supabase';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
}

export default function MissionControl() {
    const [projection, setProjection] = useState<'globe' | 'mercator'>('globe');
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);

    // Fetch balloon counts from Supabase
    useEffect(() => {
        async function fetchFleetStatus() {
            // Check if Supabase is configured
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                // Supabase not configured yet, skip fetching
                return;
            }

            try {
                const supabase = createClient();
                
                // Get active balloons (recent telemetry within last hour)
                const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                
                const { data: active, error: activeError, count } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact' })
                    .gte('time', oneHourAgo)
                    .gt('altitude_m', 100);
                
                if (!activeError) {
                    // Count distinct device_ids
                    if (active && active.length > 0) {
                        const distinctDevices = new Set(active.map((row: any) => row.device_id));
                        setActiveCount(distinctDevices.size);
                    } else if (count !== null) {
                        // Fallback to count if available
                        setActiveCount(count);
                    } else {
                        setActiveCount(0);
                    }
                }

                // Get landed balloons (altitude < 100m in last 24 hours)
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                
                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact', head: true })
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (!landedError && landed) {
                    setLandedCount(landed.length || 0);
                }

                // Also fetch balloon positions for the map
                // Get all active balloons (within last 2 hours to catch more test data)
                const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                const { data: balloons, error: balloonsError } = await supabase
                    .from('telemetry')
                    .select('device_id, lat, lon, altitude_m, time')
                    .gte('time', twoHoursAgo)
                    .gt('altitude_m', 100)
                    .order('time', { ascending: false });

                if (!balloonsError && balloons) {
                    // Get latest telemetry per device
                    const latestByDevice = new Map<string, BalloonData>();
                    balloons.forEach((row: any) => {
                        if (!latestByDevice.has(row.device_id)) {
                            latestByDevice.set(row.device_id, {
                                id: row.device_id,
                                lat: row.lat,
                                lon: row.lon,
                                altitude_m: row.altitude_m,
                            });
                        }
                    });
                    setBalloonData(Array.from(latestByDevice.values()));
                    console.log('Balloons for map:', Array.from(latestByDevice.values()));
                }
            } catch (error) {
                // Silently handle Supabase errors if not configured
                console.debug('Supabase not configured or error:', error);
            }
        }

        fetchFleetStatus();
        // Refresh every 30 seconds
        const interval = setInterval(fetchFleetStatus, 30000);
        
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="w-screen h-screen relative overflow-hidden">
            {/* Full-screen 3D Map */}
            <div className="absolute inset-0">
                <MissionMap 
                    projection={projection}
                    onProjectionChange={setProjection}
                    balloonData={balloonData}
                />
            </div>

            {/* Glassmorphism Sidebar */}
            <div className="absolute left-0 top-0 h-full w-80 backdrop-blur-md bg-black/30 border-r border-white/10 z-10 p-6 flex flex-col">
                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-white mb-2">Mission Control</h1>
                    <p className="text-gray-400 text-sm">Stratolink Fleet Dashboard</p>
                </div>

                {/* Fleet Status */}
                <div className="mb-8 space-y-4">
                    <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-gray-400 text-sm">Active Balloons</span>
                            <span className="text-cyan-400 text-2xl font-bold">{activeCount}</span>
                        </div>
                    </div>
                    <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-gray-400 text-sm">Landed</span>
                            <span className="text-gray-400 text-2xl font-bold">{landedCount}</span>
                        </div>
                    </div>
                </div>

                {/* Projection Toggle */}
                <div className="mt-auto">
                    <button
                        onClick={() => setProjection(projection === 'globe' ? 'mercator' : 'globe')}
                        className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/50 text-cyan-400 px-4 py-3 rounded-lg font-medium transition-colors"
                    >
                        {projection === 'globe' ? 'Switch to 2D' : 'Switch to 3D Globe'}
                    </button>
                </div>
            </div>
        </div>
    );
}
