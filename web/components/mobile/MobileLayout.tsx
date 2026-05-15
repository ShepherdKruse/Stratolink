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
    launcher_name?: string;
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
        if (typeof window !== 'undefined' && navigator?.geolocation) {
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
            // Skip if in iframe preview mode (no Supabase access needed)
            if (typeof window !== 'undefined' && window.self !== window.top) {
                return;
            }
            
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                return;
            }

            try {
                const supabase = createClient();
                
                // Fetch activated devices (only 'flying' status for display)
                const { data: activatedDevices } = await supabase
                    .from('devices')
                    .select('device_id, launcher_name, status, launch_lat, launch_lon')
                    .eq('status', 'flying');

                const activatedDeviceIds = activatedDevices ? activatedDevices.map((d: any) => d.device_id) : [];
                const launcherMap = new Map<string, string>();
                const launchLocationMap = new Map<string, { lat: number; lon: number }>();
                
                // Create launcher name and launch location maps
                if (activatedDevices) {
                    activatedDevices.forEach((d: any) => {
                        launcherMap.set(d.device_id, d.launcher_name || 'Unknown');
                        if (d.launch_lat && d.launch_lon) {
                            launchLocationMap.set(d.device_id, { lat: d.launch_lat, lon: d.launch_lon });
                        }
                    });
                }

                if (activatedDeviceIds.length > 0) {
                    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                    
                    // Get active count (only for activated devices)
                    const { data: active, error: activeError } = await supabase
                        .from('telemetry')
                        .select('device_id')
                        .in('device_id', activatedDeviceIds)
                        .gte('time', twoHoursAgo)
                        .gt('altitude_m', 100);
                    
                    if (!activeError && active) {
                        const distinctDevices = new Set(active.map((row: any) => row.device_id));
                        setActiveCount(distinctDevices.size);
                    }

                    // Get landed count (only for activated devices)
                    const { data: landed, error: landedError } = await supabase
                        .from('telemetry')
                        .select('device_id')
                        .in('device_id', activatedDeviceIds)
                        .gte('time', oneDayAgo)
                        .lt('altitude_m', 100);
                    
                    if (!landedError && landed) {
                        const distinctLanded = new Set(landed.map((row: any) => row.device_id));
                        setLandedCount(distinctLanded.size);
                    }
                } else {
                    setActiveCount(0);
                    setLandedCount(0);
                }

                // Fetch balloon positions (only for activated devices)
                if (activatedDeviceIds.length > 0) {
                    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                    
                    const { data: balloons, error: balloonsError } = await supabase
                        .from('telemetry')
                        .select('device_id, lat, lon, altitude_m, time, velocity_x, velocity_y')
                        .in('device_id', activatedDeviceIds)
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
                                    launcher_name: launcherMap.get(row.device_id),
                                });
                            }
                        });
                        
                        // Add devices that are activated but don't have telemetry yet (use launch location)
                        activatedDeviceIds.forEach((deviceId: string) => {
                            if (!latestByDevice.has(deviceId)) {
                                const launchLoc = launchLocationMap.get(deviceId);
                                if (launchLoc) {
                                    latestByDevice.set(deviceId, {
                                        id: deviceId,
                                        lat: launchLoc.lat,
                                        lon: launchLoc.lon,
                                        altitude_m: 0, // Ground level until first telemetry
                                        velocity_heading: 90,
                                        battery_voltage: 3.7,
                                        launcher_name: launcherMap.get(deviceId),
                                    });
                                }
                            }
                        });
                        
                        setBalloonData(Array.from(latestByDevice.values()));
                    } else {
                        // No telemetry data, but we have activated devices - use launch locations
                        const launchLocationBalloons: BalloonData[] = [];
                        activatedDeviceIds.forEach((deviceId: string) => {
                            const launchLoc = launchLocationMap.get(deviceId);
                            if (launchLoc) {
                                launchLocationBalloons.push({
                                    id: deviceId,
                                    lat: launchLoc.lat,
                                    lon: launchLoc.lon,
                                    altitude_m: 0,
                                    velocity_heading: 90,
                                    battery_voltage: 3.7,
                                    launcher_name: launcherMap.get(deviceId),
                                });
                            }
                        });
                        setBalloonData(launchLocationBalloons);
                    }
                } else {
                    // No activated devices
                    setBalloonData([]);
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

    // Flight path (map polyline) AND full per-row telemetry (sensor sheet).
    const [flightPathData, setFlightPathData] = useState<Array<{ lat: number; lon: number; time: Date }>>([]);
    const [sheetTelemetry, setSheetTelemetry] = useState<Array<Record<string, any>>>([]);

    useEffect(() => {
        async function fetchFlightPath() {
            if (!selectedBalloonId) {
                setFlightPathData([]);
                setSheetTelemetry([]);
                return;
            }

            if (typeof window !== 'undefined' && window.self !== window.top) {
                setFlightPathData([]);
                setSheetTelemetry([]);
                return;
            }

            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                return;
            }

            try {
                const supabase = createClient();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

                const cols =
                    'time, lat, lon, altitude_m, battery_voltage, solar_voltage, temperature, pressure, ' +
                    'rssi, snr, gps_speed, gps_heading, gps_satellites, mems_accel_x, mems_accel_y, mems_accel_z, ' +
                    'uv_index, ambient_lux, acoustic_event, firmware_version, uptime_s, tx_count, hdop, ' +
                    'power_mode, sleep_ms, lora_sf, lora_bw, frequency_hz';

                const { data: pathData, error } = await supabase
                    .from('telemetry')
                    .select(cols)
                    .eq('device_id', selectedBalloonId)
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: true });

                if (!error && pathData && pathData.length > 0) {
                    setSheetTelemetry(pathData as Array<Record<string, any>>);
                    const path = (pathData as any[])
                        .filter(r => r.lat !== null && r.lon !== null)
                        .map(r => ({ lat: r.lat as number, lon: r.lon as number, time: new Date(r.time) }));
                    setFlightPathData(path);
                } else {
                    setFlightPathData([]);
                    setSheetTelemetry([]);
                }
            } catch (error) {
                console.debug('Error fetching flight path:', error);
            }
        }

        fetchFlightPath();
        const interval = selectedBalloonId ? setInterval(fetchFlightPath, 15000) : null;
        return () => { if (interval) clearInterval(interval); };
    }, [selectedBalloonId]);

    const handleBalloonClick = (balloonId: string) => {
        setSelectedBalloonId(balloonId);
        // Switch to Radar tab to see the map when a balloon is selected
        setActiveTab('radar');
    };

    const handleLaunch = () => {
        // Navigate to activation page
        window.location.href = '/activate';
    };

    const handleCloseSheet = () => {
        setSelectedBalloonId(null);
    };

    // Check if we're in an iframe (for showcase preview)
    const isInIframe = typeof window !== 'undefined' && window.self !== window.top;

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
                    balloonData={{
                        altitude_m: selectedBalloon.altitude_m,
                        lat: selectedBalloon.lat,
                        lon: selectedBalloon.lon,
                        battery_voltage: selectedBalloon.battery_voltage,
                        velocity_heading: selectedBalloon.velocity_heading,
                        launcher_name: selectedBalloon.launcher_name,
                    }}
                    telemetryData={sheetTelemetry.map((row: any) => ({
                        time: row.time,
                        battery_voltage: row.battery_voltage ?? undefined,
                        solar_voltage: row.solar_voltage ?? undefined,
                        temperature: row.temperature ?? undefined,
                        pressure: row.pressure ?? undefined,
                        rssi: row.rssi ?? undefined,
                        snr: row.snr ?? undefined,
                        lat: row.lat ?? undefined,
                        lon: row.lon ?? undefined,
                        altitude_m: row.altitude_m ?? undefined,
                        gps_speed: row.gps_speed ?? undefined,
                        gps_heading: row.gps_heading ?? undefined,
                        gps_satellites: row.gps_satellites ?? undefined,
                        uv_index: row.uv_index ?? undefined,
                        ambient_lux: row.ambient_lux ?? undefined,
                        acoustic_event: row.acoustic_event ?? undefined,
                        mems_accel_x: row.mems_accel_x ?? undefined,
                        mems_accel_y: row.mems_accel_y ?? undefined,
                        mems_accel_z: row.mems_accel_z ?? undefined,
                        firmware_version: row.firmware_version ?? undefined,
                        uptime_s: row.uptime_s ?? undefined,
                        tx_count: row.tx_count ?? undefined,
                        hdop: row.hdop ?? undefined,
                        power_mode: row.power_mode ?? undefined,
                        sleep_ms: row.sleep_ms ?? undefined,
                        lora_sf: row.lora_sf ?? undefined,
                        lora_bw: row.lora_bw ?? undefined,
                        frequency_hz: row.frequency_hz ?? undefined,
                    }))}
                />
            )}

            {/* Bottom Navigation - Fixed at bottom */}
            <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
        </div>
    );
}
