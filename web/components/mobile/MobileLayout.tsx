'use client';

import { useState, useEffect } from 'react';
import { createClient } from '@/lib/supabase';
import { isValidWgs84Point } from '@/lib/mapGeo';
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
    battery_voltage?: number | null;
    launcher_name?: string;
    awaiting_gps?: boolean;
    last_contact?: string;
}

type TelemetryRow = {
    device_id: string;
    lat?: number | null;
    lon?: number | null;
    altitude_m?: number | null;
    time?: string | null;
    velocity_x?: number | null;
    velocity_y?: number | null;
    battery_voltage?: number | null;
};

interface MobileLayoutProps {
    initialBalloonId?: string | null;
}

export default function MobileLayout({ initialBalloonId = null }: MobileLayoutProps = {}) {
    const [activeTab, setActiveTab] = useState<Tab>('radar');
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);
    const [selectedBalloonId, setSelectedBalloonId] = useState<string | null>(initialBalloonId);
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);
    const [fleetRegisteredCount, setFleetRegisteredCount] = useState(0);
    const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'error'>('disconnected');
    const [lastUpdate, setLastUpdate] = useState<Date | undefined>();

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

    // Fetch balloon data — same telemetry semantics as dashboard (flying fleet, GPS + launch fallback, real sensors).
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

                const { data: activatedDevices, error: devicesError } = await supabase
                    .from('devices')
                    .select('device_id, launcher_name, status, launch_lat, launch_lon, launched_at')
                    .eq('status', 'flying');

                if (devicesError) {
                    console.error('Error fetching activated devices:', devicesError);
                    setConnectionStatus('error');
                }

                const activatedDeviceIds = activatedDevices ? activatedDevices.map((d: { device_id: string }) => d.device_id) : [];
                setFleetRegisteredCount(activatedDeviceIds.length);
                const launcherMap = new Map<string, string>();
                const launchLocationMap = new Map<string, { lat: number; lon: number }>();

                if (activatedDevices) {
                    activatedDevices.forEach((d: { device_id: string; launcher_name?: string | null; launch_lat?: number | null; launch_lon?: number | null }) => {
                        launcherMap.set(d.device_id, d.launcher_name || 'Unknown');
                        if (
                            typeof d.launch_lat === 'number' &&
                            typeof d.launch_lon === 'number' &&
                            isValidWgs84Point(d.launch_lat, d.launch_lon)
                        ) {
                            launchLocationMap.set(d.device_id, { lat: d.launch_lat, lon: d.launch_lon });
                        }
                    });
                }

                if (activatedDeviceIds.length === 0) {
                    setActiveCount(0);
                    setLandedCount(0);
                    setBalloonData([]);
                    setLastUpdate(new Date());
                    return;
                }

                const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

                const lastContactMap = new Map<string, string>();

                const { data: active, error: activeError } = await supabase
                    .from('telemetry')
                    .select('device_id, time')
                    .in('device_id', activatedDeviceIds)
                    .gte('time', twoHoursAgo);

                if (!activeError && active) {
                    const distinctDevices = new Set<string>();
                    active.forEach((row: { device_id: string; time: string }) => {
                        distinctDevices.add(row.device_id);
                        const prev = lastContactMap.get(row.device_id);
                        if (!prev || row.time > prev) lastContactMap.set(row.device_id, row.time);
                    });
                    setActiveCount(distinctDevices.size);
                } else {
                    setActiveCount(0);
                }

                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id')
                    .in('device_id', activatedDeviceIds)
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);

                if (landedError) {
                    console.error('Error fetching landed balloons:', landedError);
                } else if (landed && landed.length > 0) {
                    setLandedCount(new Set(landed.map((row: { device_id: string }) => row.device_id)).size);
                } else {
                    setLandedCount(0);
                }

                const { data: telemetryRows, error: telemetryError } = await supabase
                    .from('telemetry')
                    .select('device_id, lat, lon, altitude_m, time, velocity_x, velocity_y, battery_voltage')
                    .in('device_id', activatedDeviceIds)
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: false });

                if (telemetryError) {
                    console.error('Error fetching telemetry for map:', telemetryError);
                    setConnectionStatus('error');
                    setBalloonData([]);
                    setLastUpdate(new Date());
                    return;
                }

                const latestAny = new Map<string, TelemetryRow>();
                const latestGps = new Map<string, TelemetryRow>();
                for (const row of (telemetryRows || []) as TelemetryRow[]) {
                    if (!row.device_id) continue;
                    if (!latestAny.has(row.device_id)) latestAny.set(row.device_id, row);
                    if (isValidWgs84Point(row.lat ?? NaN, row.lon ?? NaN) && !latestGps.has(row.device_id)) {
                        latestGps.set(row.device_id, row);
                    }
                }

                const built: BalloonData[] = [];
                for (const deviceId of activatedDeviceIds) {
                    const gps = latestGps.get(deviceId);
                    const anyRow = latestAny.get(deviceId);
                    const launchLoc = launchLocationMap.get(deviceId);

                    let lat: number;
                    let lon: number;
                    let awaiting_gps = false;

                    if (gps && isValidWgs84Point(gps.lat as number, gps.lon as number)) {
                        lat = gps.lat as number;
                        lon = gps.lon as number;
                    } else if (launchLoc) {
                        lat = launchLoc.lat;
                        lon = launchLoc.lon;
                        awaiting_gps = true;
                    } else {
                        continue;
                    }

                    let velocity_heading = 90;
                    const velRow = gps ?? anyRow;
                    if (velRow?.velocity_x != null && velRow?.velocity_y != null) {
                        const headingRad = Math.atan2(velRow.velocity_x, velRow.velocity_y);
                        velocity_heading = ((headingRad * 180) / Math.PI + 360) % 360;
                    }

                    const altitude_m = (gps?.altitude_m ?? anyRow?.altitude_m ?? 0) as number;

                    built.push({
                        id: deviceId,
                        lat,
                        lon,
                        altitude_m,
                        velocity_heading,
                        battery_voltage: anyRow?.battery_voltage ?? null,
                        launcher_name: launcherMap.get(deviceId),
                        awaiting_gps,
                        last_contact: lastContactMap.get(deviceId) ?? anyRow?.time ?? undefined,
                    });
                }

                setBalloonData(built);
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
                    setSheetTelemetry(pathData as unknown as Array<Record<string, any>>);
                    const rows = pathData as unknown as Array<{ lat?: number | null; lon?: number | null; time: string }>;
                    const path = rows
                        .filter((r) => isValidWgs84Point(Number(r.lat), Number(r.lon)))
                        .map((r) => ({ lat: Number(r.lat), lon: Number(r.lon), time: new Date(r.time) }));
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

    return (
        <div className="w-screen h-screen relative overflow-hidden bg-[#1a1a1a]">
            {/* Tab Content - Full height with bottom padding for nav */}
            <div className="h-full pb-16">
                {activeTab === 'radar' && (
                    <MobileRadar
                        balloonData={balloonData}
                        flightPathData={flightPathData}
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
                        totalTracked={fleetRegisteredCount}
                        connectionStatus={connectionStatus}
                        lastUpdate={lastUpdate}
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
                        battery_voltage: selectedBalloon.battery_voltage ?? undefined,
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
