'use client';

import { useState, useEffect } from 'react';
import { createClient } from '@/lib/supabase';
import BottomNav from './BottomNav';
import BottomSheet from './BottomSheet';
import MobileRadar from './MobileRadar';
import MobileMissions from './MobileMissions';
import MobileIntel from './MobileIntel';

type Tab = 'radar' | 'missions' | 'intel';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
    velocity_heading?: number;
    battery_voltage?: number;
}

interface MobileLayoutProps {
    initialBalloonId?: string | null;
}

export default function MobileLayout({ initialBalloonId = null }: MobileLayoutProps = {}) {
    const [activeTab, setActiveTab] = useState<Tab>('radar');
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);
    const [selectedBalloonId, setSelectedBalloonId] = useState<string | null>(initialBalloonId);
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);
    const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null);

    // Auto-select balloon if initialBalloonId is provided
    useEffect(() => {
        if (initialBalloonId) {
            setSelectedBalloonId(initialBalloonId);
            setActiveTab('radar');
        }
    }, [initialBalloonId]);

    // Get user location for "Nearest" calculation
    useEffect(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setUserLocation({
                        lat: position.coords.latitude,
                        lon: position.coords.longitude,
                    });
                },
                () => {
                    // Silent fail - user location is optional
                }
            );
        }
    }, []);

    // Fetch balloon data
    useEffect(() => {
        async function fetchFleetStatus() {
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                return;
            }

            try {
                const supabase = createClient();
                
                const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                
                // Get active count
                const { data: active, error: activeError } = await supabase
                    .from('telemetry')
                    .select('device_id')
                    .gte('time', twoHoursAgo)
                    .gt('altitude_m', 100);
                
                if (!activeError && active) {
                    const distinctDevices = new Set(active.map((row: any) => row.device_id));
                    setActiveCount(distinctDevices.size);
                }

                // Get landed count
                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id')
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (!landedError && landed) {
                    const distinctLanded = new Set(landed.map((row: any) => row.device_id));
                    setLandedCount(distinctLanded.size);
                }

                // Fetch balloon positions
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

    // Get selected balloon data
    const selectedBalloon = selectedBalloonId 
        ? balloonData.find(b => b.id === selectedBalloonId) || null
        : null;

    // Fetch flight path for selected balloon
    const [flightPathData, setFlightPathData] = useState<Array<{ lat: number; lon: number; time: Date }>>([]);
    
    useEffect(() => {
            async function fetchFlightPath() {
                if (!selectedBalloonId) {
                    setFlightPathData([]);
                    return;
                }

            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                return;
            }

            try {
                const supabase = createClient();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                
                // Fetch flight path data
                const { data: pathData, error } = await supabase
                    .from('telemetry')
                    .select('lat, lon, time')
                    .eq('device_id', selectedBalloonId)
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: true });

                if (!error && pathData && pathData.length > 0) {
                    const path = pathData.map((row: any) => ({
                        lat: row.lat,
                        lon: row.lon,
                        time: new Date(row.time) as Date,
                    }));
                    setFlightPathData(path);
                } else {
                    setFlightPathData([]);
                }
            } catch (error) {
                console.debug('Error fetching flight path:', error);
            }
        }

        fetchFlightPath();
    }, [selectedBalloonId]);

    const handleBalloonClick = (balloonId: string) => {
        setSelectedBalloonId(balloonId);
        // Switch to Radar tab to see the map when a balloon is selected
        setActiveTab('radar');
    };

    const handleLaunch = () => {
        // TODO: Implement launch flow (card swiper)
        console.log('Launch new mission');
    };

    const handleCloseSheet = () => {
        setSelectedBalloonId(null);
    };

    return (
        <div className="w-screen h-screen relative overflow-hidden bg-[#1a1a1a]">
            {/* Tab Content - Full height with bottom padding for nav */}
            <div className="h-full pb-16">
                {activeTab === 'radar' && (
                    <MobileRadar
                        balloonData={balloonData}
                        onBalloonClick={handleBalloonClick}
                        userLocation={userLocation}
                        selectedBalloonId={selectedBalloonId}
                    />
                )}

                {activeTab === 'missions' && (
                    <MobileMissions
                        balloonData={balloonData}
                        onBalloonClick={handleBalloonClick}
                        onLaunch={handleLaunch}
                    />
                )}

                {activeTab === 'intel' && (
                    <MobileIntel
                        activeCount={activeCount}
                        landedCount={landedCount}
                        totalTracked={balloonData.length}
                        balloonData={balloonData}
                    />
                )}
            </div>

            {/* Bottom Sheet - Shows when balloon is selected */}
            {selectedBalloon && (
                <BottomSheet
                    isOpen={!!selectedBalloonId}
                    onClose={handleCloseSheet}
                    balloonId={selectedBalloonId!}
                    balloonData={selectedBalloon}
                    telemetryData={flightPathData.length > 0 ? flightPathData.map(point => ({
                        time: point.time,
                        battery_voltage: 3.7 + Math.random() * 0.5,
                        temperature: -45 + Math.random() * 10,
                        pressure: 120 + Math.random() * 20,
                        rssi: -112 + Math.random() * 10,
                    })) : []}
                />
            )}

            {/* Bottom Navigation - Fixed at bottom */}
            <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
        </div>
    );
}
