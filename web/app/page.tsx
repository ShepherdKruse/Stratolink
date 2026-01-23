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
    const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
    const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'error'>('disconnected');

    // Fetch balloon counts from Supabase
    useEffect(() => {
        async function fetchFleetStatus() {
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                setConnectionStatus('disconnected');
                return;
            }

            try {
                const supabase = createClient();
                setConnectionStatus('connected');
                
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

                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id')
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (landedError) {
                    console.error('Error fetching landed balloons:', landedError);
                } else {
                    if (landed && landed.length > 0) {
                        const distinctLanded = new Set(landed.map((row: any) => row.device_id));
                        setLandedCount(distinctLanded.size);
                    } else {
                        setLandedCount(0);
                    }
                }

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
                    const processedBalloons = Array.from(latestByDevice.values());
                    setBalloonData(processedBalloons);
                } else if (balloonsError) {
                    console.error('Error fetching balloons:', balloonsError);
                    setConnectionStatus('error');
                }
                
                setLastUpdate(new Date());
            } catch (error) {
                console.debug('Supabase not configured or error:', error);
                setConnectionStatus('error');
            }
        }

        fetchFleetStatus();
        const interval = setInterval(fetchFleetStatus, 30000);
        
        return () => clearInterval(interval);
    }, []);

    const activeBalloon = activeBalloonId 
        ? balloonData.find(b => b.id === activeBalloonId) || null
        : null;

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
                    const lastTime = path[path.length - 1].time;
                    setPlaybackTime(lastTime instanceof Date ? lastTime : new Date(lastTime));
                } else if (error) {
                    console.error('Error fetching flight path:', error);
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

    const timelineStart: Date = flightPathData.length > 0 
        ? (flightPathData[0].time instanceof Date ? flightPathData[0].time : new Date(flightPathData[0].time))
        : new Date();
    const timelineEnd: Date = flightPathData.length > 0
        ? (flightPathData[flightPathData.length - 1].time instanceof Date 
            ? flightPathData[flightPathData.length - 1].time 
            : new Date(flightPathData[flightPathData.length - 1].time))
        : new Date();
    const currentPlaybackTime: Date = playbackTime || timelineEnd;

    const handleExitRideAlong = () => {
        setActiveBalloonId(null);
        setIsSidebarOpen(false);
    };

    const toggleSidebar = () => {
        if (activeBalloonId) {
            setIsSidebarOpen(prev => !prev);
        }
    };

    // Format timestamp for display
    const formatTime = (date: Date) => {
        return date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    };

    // Client-side only timestamp to avoid hydration mismatch
    const [currentTime, setCurrentTime] = useState<string>('');
    useEffect(() => {
        setCurrentTime(formatTime(new Date()));
        const interval = setInterval(() => {
            setCurrentTime(formatTime(new Date()));
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="w-screen h-screen relative overflow-hidden bg-[#1a1a1a]">
            {/* Full-screen Map */}
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

            {/* Dense Information Sidebar - Visible when no balloon selected */}
            {!activeBalloonId && (
                <div className="absolute left-0 top-0 h-full w-[280px] bg-[#1a1a1a] border-r border-[#333] z-10 flex flex-col text-[12px]">
                    {/* Header - compact */}
                    <div className="p-3 border-b border-[#333]">
                        <div className="flex items-baseline justify-between">
                            <h1 className="text-[14px] font-semibold text-[#e5e5e5]">Stratolink</h1>
                            <span className="text-[10px] text-[#666] font-mono">v1.0.0</span>
                        </div>
                        <p className="text-[#666] text-[10px] mt-1">Pico-Balloon Telemetry System</p>
                    </div>

                    {/* System Status - dense */}
                    <div className="p-3 border-b border-[#333]">
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">System Status</div>
                        <div className="space-y-1 font-mono text-[11px]">
                            <div className="flex justify-between">
                                <span className="text-[#999]">Database</span>
                                <span className={connectionStatus === 'connected' ? 'text-[#4a9]' : connectionStatus === 'error' ? 'text-[#c44]' : 'text-[#b84]'}>
                                    {connectionStatus.toUpperCase()}
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-[#999]">Last Update</span>
                                <span className="text-[#e5e5e5]">{lastUpdate.toISOString().substring(11, 19)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-[#999]">Refresh</span>
                                <span className="text-[#e5e5e5]">30s</span>
                            </div>
                        </div>
                    </div>

                    {/* Fleet Overview - data table style */}
                    <div className="p-3 border-b border-[#333]">
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Fleet Overview</div>
                        <table className="w-full font-mono text-[11px]">
                            <tbody>
                                <tr>
                                    <td className="text-[#999] py-1">Active (alt &gt;100m)</td>
                                    <td className="text-right text-[#4a90d9] font-semibold">{activeCount}</td>
                                </tr>
                                <tr>
                                    <td className="text-[#999] py-1">Landed (alt ≤100m)</td>
                                    <td className="text-right text-[#e5e5e5]">{landedCount}</td>
                                </tr>
                                <tr>
                                    <td className="text-[#999] py-1">Total Tracked</td>
                                    <td className="text-right text-[#e5e5e5]">{balloonData.length}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    {/* Active Devices List */}
                    <div className="flex-1 overflow-hidden flex flex-col">
                        <div className="p-3 pb-2">
                            <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider">
                                Active Devices ({balloonData.length})
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto px-3 pb-3">
                            {balloonData.length === 0 ? (
                                <div className="text-[#666] text-[11px] font-mono py-2">
                                    No devices in range
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {balloonData.map((balloon) => (
                                        <button
                                            key={balloon.id}
                                            onClick={() => setActiveBalloonId(balloon.id)}
                                            className="w-full text-left p-2 border border-[#333] hover:border-[#4a90d9] hover:bg-[#242424] transition-colors"
                                        >
                                            <div className="flex items-baseline justify-between mb-1">
                                                <span className="font-mono text-[11px] text-[#e5e5e5] font-semibold">
                                                    {balloon.id}
                                                </span>
                                                <span className={`text-[10px] ${balloon.altitude_m > 100 ? 'text-[#4a9]' : 'text-[#666]'}`}>
                                                    {balloon.altitude_m > 100 ? 'ACTIVE' : 'LANDED'}
                                                </span>
                                            </div>
                                            <div className="font-mono text-[10px] text-[#999] space-y-0.5">
                                                <div>{balloon.lat.toFixed(4)}°, {balloon.lon.toFixed(4)}°</div>
                                                <div>Alt: {balloon.altitude_m.toLocaleString()}m ({(balloon.altitude_m * 3.28084).toLocaleString(undefined, { maximumFractionDigits: 0 })}ft)</div>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* View Controls - bottom */}
                    <div className="p-3 border-t border-[#333]">
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">View Controls</div>
                        <div className="flex gap-1">
                            <button
                                onClick={() => setProjection('globe')}
                                className={`flex-1 py-1.5 px-2 text-[11px] font-mono border transition-colors ${
                                    projection === 'globe' 
                                        ? 'border-[#4a90d9] bg-[#4a90d9]/10 text-[#4a90d9]' 
                                        : 'border-[#333] text-[#999] hover:border-[#666]'
                                }`}
                            >
                                3D Globe
                            </button>
                            <button
                                onClick={() => setProjection('mercator')}
                                className={`flex-1 py-1.5 px-2 text-[11px] font-mono border transition-colors ${
                                    projection === 'mercator' 
                                        ? 'border-[#4a90d9] bg-[#4a90d9]/10 text-[#4a90d9]' 
                                        : 'border-[#333] text-[#999] hover:border-[#666]'
                                }`}
                            >
                                2D Map
                            </button>
                        </div>
                    </div>

                    {/* Footer - timestamp */}
                    <div className="p-2 border-t border-[#333] bg-[#141414]">
                        <div className="font-mono text-[9px] text-[#666] text-center">
                            {currentTime || '—'}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
