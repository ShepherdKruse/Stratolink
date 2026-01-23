'use client';

import { useState, useEffect } from 'react';
import MissionMap from '@/components/dashboard/MissionMap';
import PilotHUD from '@/components/dashboard/PilotHUD';
import MissionSidebar from '@/components/dashboard/MissionSidebar';
import MissionTimeline from '@/components/dashboard/MissionTimeline';
import { createClient } from '@/lib/supabase';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
    velocity_heading?: number;
    battery_voltage?: number;
}

export default function DashboardClient() {
    const [mapboxToken, setMapboxToken] = useState<string>('');
    const [projection, setProjection] = useState<'globe' | 'mercator'>('globe');
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);
    const [activeBalloonId, setActiveBalloonId] = useState<string | null>(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [playbackTime, setPlaybackTime] = useState<Date | null>(null);
    const [flightPathData, setFlightPathData] = useState<Array<{ lat: number; lon: number; time: Date }>>([]);

    // Fetch Mapbox token from API
    useEffect(() => {
        async function fetchToken() {
            try {
                const res = await fetch('/api/mapbox-token');
                const data = await res.json();
                console.log('[v0] Mapbox token response:', data.token ? 'Token received' : 'No token');
                setMapboxToken(data.token || '');
            } catch (error) {
                console.log('[v0] Error fetching Mapbox token:', error);
            }
        }
        fetchToken();
    }, []);

    // Fetch balloon counts from Supabase
    useEffect(() => {
        async function fetchFleetStatus() {
            try {
                const supabase = createClient();
                
                // Get active balloons (recent telemetry within last 2 hours)
                const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                
                const { data: active, error: activeError, count } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact' })
                    .gte('time', twoHoursAgo)
                    .gt('altitude_m', 100);
                
                if (!activeError) {
                    if (active && active.length > 0) {
                        const distinctDevices = new Set(active.map((row: any) => row.device_id));
                        setActiveCount(distinctDevices.size);
                    } else if (count !== null) {
                        setActiveCount(count);
                    } else {
                        setActiveCount(0);
                    }
                }

                // Get landed balloons (altitude < 100m in last 24 hours)
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id')
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (!landedError && landed && landed.length > 0) {
                    const distinctLanded = new Set(landed.map((row: any) => row.device_id));
                    setLandedCount(distinctLanded.size);
                } else {
                    setLandedCount(0);
                }

                // Also fetch balloon positions for the map
                const { data: balloons, error: balloonsError } = await supabase
                    .from('telemetry')
                    .select('device_id, lat, lon, altitude_m, time, velocity_x, velocity_y')
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: false });

                if (!balloonsError && balloons) {
                    const latestByDevice = new Map<string, BalloonData>();
                    balloons.forEach((row: any) => {
                        if (!latestByDevice.has(row.device_id)) {
                            let velocity_heading = 90;
                            if (row.velocity_x !== null && row.velocity_y !== null) {
                                const headingRad = Math.atan2(row.velocity_x, row.velocity_y);
                                velocity_heading = (headingRad * 180 / Math.PI + 360) % 360;
                            }
                            
                            latestByDevice.set(row.device_id, {
                                id: row.device_id,
                                lat: row.lat,
                                lon: row.lon,
                                altitude_m: row.altitude_m,
                                velocity_heading: velocity_heading,
                                battery_voltage: 3.7,
                            });
                        }
                    });
                    setBalloonData(Array.from(latestByDevice.values()));
                }
            } catch (error) {
                console.debug('Supabase not configured or error:', error);
            }
        }

        fetchFleetStatus();
        const interval = setInterval(fetchFleetStatus, 30000);
        return () => clearInterval(interval);
    }, []);

    // Get active balloon data for HUD
    const activeBalloon = activeBalloonId 
        ? balloonData.find(b => b.id === activeBalloonId) || null
        : null;

    // Fetch flight path data when active balloon changes
    useEffect(() => {
        async function fetchFlightPath() {
            if (!activeBalloonId) {
                setFlightPathData([]);
                setPlaybackTime(null);
                return;
            }

            try {
                const supabase = createClient();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                
                const { data: pathData, error } = await supabase
                    .from('telemetry')
                    .select('lat, lon, time, altitude_m')
                    .eq('device_id', activeBalloonId)
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: true });

                if (!error && pathData && pathData.length > 0) {
                    const path = pathData.map((row: any) => ({
                        lat: row.lat,
                        lon: row.lon,
                        time: new Date(row.time) as Date,
                    }));
                    setFlightPathData(path);
                    
                    const lastTime = path[path.length - 1].time;
                    setPlaybackTime(lastTime instanceof Date ? lastTime : new Date(lastTime));
                } else {
                    setFlightPathData([]);
                    setPlaybackTime(null);
                }
            } catch (error) {
                console.debug('Error fetching flight path:', error);
            }
        }

        fetchFlightPath();
    }, [activeBalloonId]);

    // Get time range for timeline
    const timelineStart: Date = flightPathData.length > 0 
        ? (flightPathData[0].time instanceof Date ? flightPathData[0].time : new Date(flightPathData[0].time))
        : new Date();
    const timelineEnd: Date = flightPathData.length > 0
        ? (flightPathData[flightPathData.length - 1].time instanceof Date 
            ? flightPathData[flightPathData.length - 1].time 
            : new Date(flightPathData[flightPathData.length - 1].time))
        : new Date();
    const currentPlaybackTime: Date = playbackTime || timelineEnd;

    // Exit Ride Along mode
    const handleExitRideAlong = () => {
        setActiveBalloonId(null);
        setIsSidebarOpen(false);
    };

    // Toggle sidebar
    const toggleSidebar = () => {
        if (activeBalloonId) {
            setIsSidebarOpen(prev => !prev);
        }
    };

    // Show loading state while token is being fetched
    if (!mapboxToken) {
        return (
            <div className="w-screen h-screen relative overflow-hidden bg-slate-900 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-cyan-400 mx-auto mb-4"></div>
                    <p className="text-white text-lg">Loading Mission Control...</p>
                    <p className="text-gray-400 text-sm mt-2">Initializing map services</p>
                </div>
            </div>
        );
    }

    return (
        <div className="w-screen h-screen relative overflow-hidden">
            {/* Full-screen 3D Map */}
            <div className="absolute inset-0">
                <MissionMap 
                    projection={projection}
                    onProjectionChange={setProjection}
                    balloonData={balloonData}
                    activeBalloonId={activeBalloonId}
                    onActiveBalloonChange={setActiveBalloonId}
                    flightPathData={flightPathData}
                    playbackTime={playbackTime}
                    mapboxToken={mapboxToken}
                />
            </div>

            {/* Pilot HUD Overlay */}
            <PilotHUD 
                activeBalloonId={activeBalloonId}
                balloonData={activeBalloon}
                onExit={handleExitRideAlong}
                onToggleSidebar={toggleSidebar}
                isSidebarOpen={isSidebarOpen}
            />

            {/* Mission Sidebar - Systems Panel */}
            {activeBalloonId && (
                <MissionSidebar
                    isOpen={isSidebarOpen}
                    onClose={() => setIsSidebarOpen(false)}
                    balloonId={activeBalloonId}
                    telemetryData={flightPathData.map(point => ({
                        time: point.time,
                        battery_voltage: 3.7 + Math.random() * 0.5,
                        temperature: -45 + Math.random() * 10,
                        pressure: 120 + Math.random() * 20,
                        rssi: -112 + Math.random() * 10,
                    }))}
                />
            )}

            {/* Mission Timeline Scrubber */}
            {activeBalloonId && flightPathData.length > 0 && (
                <MissionTimeline
                    startTime={timelineStart}
                    endTime={timelineEnd}
                    currentTime={currentPlaybackTime}
                    onChange={setPlaybackTime}
                />
            )}

            {/* Glassmorphism Sidebar - Hidden during Ride Along mode */}
            {!activeBalloonId && (
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
            )}
        </div>
    );
}
