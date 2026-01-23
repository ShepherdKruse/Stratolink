'use client';

import { useState, useEffect } from 'react';
import MissionMap from '@/components/MissionMap';
import PilotHUD from '@/components/PilotHUD';
import MissionSidebar from '@/components/MissionSidebar';
import MissionTimeline from '@/components/MissionTimeline';
import { createClient } from '@/lib/supabase';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
    velocity_heading?: number;
    battery_voltage?: number;
}

export default function MissionControl() {
    const [projection, setProjection] = useState<'globe' | 'mercator'>('globe');
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);
    const [activeBalloonId, setActiveBalloonId] = useState<string | null>(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [playbackTime, setPlaybackTime] = useState<Date | null>(null);
    const [flightPathData, setFlightPathData] = useState<Array<{ lat: number; lon: number; time: Date }>>([]);

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
                
                // Get active balloons (recent telemetry within last 2 hours)
                const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                
                const { data: active, error: activeError, count } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact' })
                    .gte('time', twoHoursAgo)
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
                    .select('device_id')
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (landedError) {
                    console.error('Error fetching landed balloons:', landedError);
                } else {
                    // Count distinct device_ids
                    if (landed && landed.length > 0) {
                        const distinctLanded = new Set(landed.map((row: any) => row.device_id));
                        setLandedCount(distinctLanded.size);
                    } else {
                        setLandedCount(0);
                    }
                }

                // Also fetch balloon positions for the map
                // Get all balloons (active and landed) within last 24 hours
                // Reuse oneDayAgo from above
                const { data: balloons, error: balloonsError } = await supabase
                    .from('telemetry')
                    .select('device_id, lat, lon, altitude_m, time, velocity_x, velocity_y')
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: false });

                if (!balloonsError && balloons) {
                    // Get latest telemetry per device
                    const latestByDevice = new Map<string, BalloonData>();
                    balloons.forEach((row: any) => {
                        if (!latestByDevice.has(row.device_id)) {
                            // Calculate heading from velocity components (in degrees, 0-360)
                            let velocity_heading = 90; // Default
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
                                battery_voltage: 3.7, // Mock data for now
                            });
                        }
                    });
                    const processedBalloons = Array.from(latestByDevice.values());
                    setBalloonData(processedBalloons);
                } else if (balloonsError) {
                    console.error('Error fetching balloons:', balloonsError);
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

            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
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
                    
                    // Debug log
                    console.log('✅ Flight path data fetched:', {
                        balloonId: activeBalloonId,
                        points: path.length,
                        firstPoint: path[0] ? { lat: path[0].lat, lon: path[0].lon, time: path[0].time.toISOString() } : null,
                        lastPoint: path[path.length - 1] ? { lat: path[path.length - 1].lat, lon: path[path.length - 1].lon, time: path[path.length - 1].time.toISOString() } : null
                    });
                    
                    // Set initial playback time to most recent
                    const lastTime = path[path.length - 1].time;
                    setPlaybackTime(lastTime instanceof Date ? lastTime : new Date(lastTime));
                } else if (error) {
                    console.error('❌ Error fetching flight path:', error);
                } else {
                    console.warn('⚠️ No flight path data found for balloon:', activeBalloonId, '- Make sure you ran flight-path-data.sql in Supabase');
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
    
    // Debug timeline
    useEffect(() => {
        if (activeBalloonId) {
            console.log('⏱️ Timeline state:', {
                hasData: flightPathData.length > 0,
                dataPoints: flightPathData.length,
                start: timelineStart.toISOString(),
                end: timelineEnd.toISOString(),
                current: currentPlaybackTime.toISOString(),
                playbackTime: playbackTime?.toISOString() || 'null'
            });
        }
    }, [playbackTime, timelineStart, timelineEnd, currentPlaybackTime, activeBalloonId, flightPathData.length]);

    // Exit Ride Along mode
    const handleExitRideAlong = () => {
        setActiveBalloonId(null);
        setIsSidebarOpen(false); // Close sidebar when exiting ride along
        // Camera reset is handled by MissionMap when activeBalloonId changes
    };

    // Toggle sidebar (only works when in Ride Along mode)
    const toggleSidebar = () => {
        if (activeBalloonId) {
            setIsSidebarOpen(prev => !prev);
        }
    };

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
                        battery_voltage: 3.7 + Math.random() * 0.5, // Mock data for now
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
