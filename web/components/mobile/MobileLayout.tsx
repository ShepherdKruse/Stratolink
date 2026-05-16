'use client';

import { useEffect, useMemo, useState } from 'react';
import '@/styles/mobile-stratolink.css';

import { createClient } from '@/lib/supabase';
import { isUsableGpsCoordinate, isValidWgs84Point } from '@/lib/mapGeo';

import MobileAlertsTab from './MobileAlertsTab';
import MobileDeviceDetailScreen from './MobileDeviceDetailScreen';
import MobileFleetScreen from './MobileFleetScreen';
import MobileMapLiveTab from './MobileMapLiveTab';
import MobileMoreTab from './MobileMoreTab';
import type { MobileMainTab } from './MobileStratolinkTabBar';
import MobileStratolinkTabBar from './MobileStratolinkTabBar';
import MobileTelemetryTab from './MobileTelemetryTab';
import { deriveFleetAlerts } from './mobileStratolinkUtils';
import type { MobileFleetDeviceRow } from './mobileStratolinkUtils';

type TelemetryRow = {
    device_id: string;
    lat?: number | null;
    lon?: number | null;
    altitude_m?: number | null;
    time?: string | null;
    velocity_x?: number | null;
    velocity_y?: number | null;
    battery_voltage?: number | null;
    rssi?: number | null;
    gps_satellites?: number | null;
};

type BalloonData = MobileFleetDeviceRow;

interface MobileLayoutProps {
    initialBalloonId?: string | null;
}

export default function MobileLayout({ initialBalloonId = null }: MobileLayoutProps = {}) {
    const [mainTab, setMainTab] = useState<MobileMainTab>('fleet');
    const [fleetMode, setFleetMode] = useState<'list' | 'detail'>('list');
    const [balloonData, setBalloonData] = useState<BalloonData[]>([]);
    const [selectedBalloonId, setSelectedBalloonId] = useState<string | null>(initialBalloonId);

    const [activeCount, setActiveCount] = useState(0);
    const [fleetRegisteredCount, setFleetRegisteredCount] = useState(0);
    const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'error'>('disconnected');
    const [lastUpdate, setLastUpdate] = useState<Date | undefined>();

    const [flightPathData, setFlightPathData] = useState<Array<{ lat: number; lon: number; time: Date }>>([]);
    const [sheetTelemetry, setSheetTelemetry] = useState<Array<Record<string, unknown>>>([]);

    useEffect(() => {
        if (initialBalloonId) {
            setSelectedBalloonId(initialBalloonId);
            setMainTab('fleet');
            setFleetMode('detail');
        }
    }, [initialBalloonId]);

    useEffect(() => {
        if (typeof window === 'undefined' || !navigator?.geolocation) return;
        navigator.geolocation.getCurrentPosition(
            (position) =>
                setUserLocation({
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                }),
            () => {},
        );
    }, []);

    useEffect(() => {
        if (mainTab === 'telemetry' && !selectedBalloonId && balloonData[0]?.id) {
            setSelectedBalloonId(balloonData[0].id);
        }
    }, [mainTab, balloonData, selectedBalloonId]);

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

                const activatedDeviceIds =
                    activatedDevices ? activatedDevices.map((d: { device_id: string }) => d.device_id) : [];
                setFleetRegisteredCount(activatedDeviceIds.length);

                const launcherMap = new Map<string, string>();
                const launchLocationMap = new Map<string, { lat: number; lon: number }>();

                if (activatedDevices) {
                    activatedDevices.forEach(
                        (d: {
                            device_id: string;
                            launcher_name?: string | null;
                            launch_lat?: number | null;
                            launch_lon?: number | null;
                        }) => {
                            launcherMap.set(d.device_id, d.launcher_name || 'Unknown');
                            if (
                                typeof d.launch_lat === 'number' &&
                                typeof d.launch_lon === 'number' &&
                                isValidWgs84Point(d.launch_lat, d.launch_lon)
                            ) {
                                launchLocationMap.set(d.device_id, {
                                    lat: d.launch_lat,
                                    lon: d.launch_lon,
                                });
                            }
                        },
                    );
                }

                if (activatedDeviceIds.length === 0) {
                    setActiveCount(0);
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

                const { data: telemetryRows, error: telemetryError } = await supabase
                    .from('telemetry')
                    .select(
                        'device_id, lat, lon, altitude_m, time, velocity_x, velocity_y, battery_voltage, rssi, gps_satellites',
                    )
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

                    if (!latestAny.has(row.device_id)) {
                        latestAny.set(row.device_id, row);
                    }

                    const hasGpsFix =
                        row.lat != null &&
                        row.lon != null &&
                        isUsableGpsCoordinate(Number(row.lat), Number(row.lon));
                    if (hasGpsFix && !latestGps.has(row.device_id)) {
                        latestGps.set(row.device_id, row);
                    }
                }

                const built: BalloonData[] = [];

                for (const deviceId of activatedDeviceIds) {
                    const gpsRow = latestGps.get(deviceId);
                    const anyRow = latestAny.get(deviceId);
                    const launchLoc = launchLocationMap.get(deviceId);

                    let lat: number;
                    let lon: number;
                    let awaiting_gps = false;

                    if (
                        gpsRow &&
                        gpsRow.lat != null &&
                        gpsRow.lon != null &&
                        isUsableGpsCoordinate(Number(gpsRow.lat), Number(gpsRow.lon))
                    ) {
                        lat = Number(gpsRow.lat);
                        lon = Number(gpsRow.lon);
                    } else if (launchLoc) {
                        lat = launchLoc.lat;
                        lon = launchLoc.lon;
                        awaiting_gps = true;
                    } else {
                        continue;
                    }

                    let velocity_heading = 90;
                    const velRow = gpsRow ?? anyRow;
                    if (velRow?.velocity_x != null && velRow?.velocity_y != null) {
                        const headingRad = Math.atan2(velRow.velocity_x!, velRow.velocity_y!);
                        velocity_heading = ((headingRad * 180) / Math.PI + 360) % 360;
                    }

                    const altitude_m = (gpsRow?.altitude_m ?? anyRow?.altitude_m ?? 0) as number;

                    built.push({
                        id: deviceId,
                        lat,
                        lon,
                        altitude_m,
                        velocity_heading,
                        battery_voltage: anyRow?.battery_voltage ?? gpsRow?.battery_voltage ?? null,
                        rssi: anyRow?.rssi ?? gpsRow?.rssi ?? null,
                        gps_satellites: gpsRow?.gps_satellites ?? anyRow?.gps_satellites ?? null,
                        launcher_name: launcherMap.get(deviceId),
                        awaiting_gps,
                        last_contact: lastContactMap.get(deviceId) ?? anyRow?.time ?? undefined,
                    });
                }

                setBalloonData(built);
                setLastUpdate(new Date());
            } catch {
                console.debug('Supabase not configured');
                setConnectionStatus('error');
            }
        }

        fetchFleetStatus();
        const interval = setInterval(fetchFleetStatus, 30000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        async function fetchTelemetryForSelectedDevice() {
            if (!selectedBalloonId) {
                setFlightPathData([]);
                setSheetTelemetry([]);
                return;
            }

            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '')
                return;

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
                    setSheetTelemetry(pathData as unknown as Array<Record<string, unknown>>);

                    const rows = pathData as unknown as Array<{
                        lat?: number | null;
                        lon?: number | null;
                        time: string;
                    }>;
                    const validPath = rows
                        .filter(
                            (row) =>
                                row.lat != null &&
                                row.lon != null &&
                                isUsableGpsCoordinate(Number(row.lat), Number(row.lon)),
                        )
                        .map((row) => ({
                            lat: Number(row.lat),
                            lon: Number(row.lon),
                            time: new Date(row.time),
                        }));
                    setFlightPathData(validPath);
                } else {
                    setFlightPathData([]);
                    setSheetTelemetry([]);
                }
            } catch {
                console.debug('telemetry fetch failure');
                setFlightPathData([]);
                setSheetTelemetry([]);
            }
        }

        fetchTelemetryForSelectedDevice();
        const interval = selectedBalloonId ? setInterval(fetchTelemetryForSelectedDevice, 15000) : null;

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [selectedBalloonId]);

    useEffect(() => {
        if (mainTab !== 'map') return;

        const first = balloonData[0]?.id;
        const stillValid = balloonData.some((b) => b.id === selectedBalloonId);

        if (!stillValid && first) setSelectedBalloonId(first);
        else if (!selectedBalloonId && first) setSelectedBalloonId(first);
    }, [mainTab, balloonData, selectedBalloonId]);

    const selectedBalloon = selectedBalloonId ? balloonData.find((b) => b.id === selectedBalloonId) ?? null : null;

    const livePacketIso = useMemo(() => {
        let best: number | null = null;
        for (const d of balloonData) {
            if (!d.last_contact) continue;

            const t = new Date(d.last_contact).getTime();
            if (Number.isNaN(t)) continue;

            if (best === null || t > best) best = t;
        }
        return best ? new Date(best).toISOString() : null;
    }, [balloonData]);

    const heuristicAlerts = useMemo(() => deriveFleetAlerts(balloonData), [balloonData]);

    const tabBarAlerts = heuristicAlerts.filter((x) => !x.resolved).length;

    const latestTelemetryRow = sheetTelemetry[sheetTelemetry.length - 1] as Record<string, unknown> | undefined;

    const body = (
        <>
            {mainTab === 'fleet' && fleetMode === 'list' ? (
                <MobileFleetScreen
                    balloonData={balloonData}
                    activeTransmittingCount={activeCount}
                    fleetRegisteredCount={fleetRegisteredCount}
                    activeAlertsCount={tabBarAlerts}
                    connectionStatus={connectionStatus}
                    livePacketIso={livePacketIso}
                    lastFleetRefreshIso={lastUpdate?.toISOString()}
                    onOpenDevice={(deviceId: string) => {
                        setSelectedBalloonId(deviceId);
                        setFleetMode('detail');
                    }}
                    onOpenLaunch={() => {
                        window.location.href = '/activate';
                    }}
                />
            ) : null}

            {mainTab === 'fleet' && fleetMode === 'detail' && selectedBalloon ? (
                <MobileDeviceDetailScreen
                    device={selectedBalloon}
                    telemetryRows={sheetTelemetry}
                    flightPathData={flightPathData}
                    onBack={() => setFleetMode('list')}
                    onOpenFullMap={() => {
                        setMainTab('map');
                        setFleetMode('list');
                    }}
                />
            ) : null}

            {mainTab === 'map' ? (
                <MobileMapLiveTab
                    balloonData={balloonData}
                    flightPathData={flightPathData}
                    selectedBalloonId={selectedBalloonId}
                    onSelectDevice={(id: string | null) => setSelectedBalloonId(id)}
                    userLocation={userLocation}
                    latestRow={latestTelemetryRow}
                />
            ) : null}

            {mainTab === 'telemetry' ? (
                <MobileTelemetryTab deviceId={selectedBalloonId || null} telemetryRows={sheetTelemetry} />
            ) : null}

            {mainTab === 'alerts' ? <MobileAlertsTab activeAlerts={heuristicAlerts} /> : null}

            {mainTab === 'more' ? (
                <MobileMoreTab
                    onLaunchMission={() => {
                        window.location.href = '/activate';
                    }}
                />
            ) : null}
        </>
    );

    return (
        <div className="sl-mobile h-screen max-h-[100dvh] w-screen max-w-[100vw] overflow-hidden bg-[var(--bg)] text-[var(--text)] antialiased selection:bg-teal-950">
            <div className="h-full">{body}</div>
            <MobileStratolinkTabBar active={mainTab} onTabChange={setMainTab} alertsBadge={tabBarAlerts} />
        </div>
    );
}
