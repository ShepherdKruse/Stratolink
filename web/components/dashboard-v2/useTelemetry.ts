/**
 * useTelemetry — bridge between Supabase telemetry rows and the v2 dashboard
 * atoms. Returns rows in the design's data vocabulary so atoms drop in 1:1.
 *
 * Strict rule: every value here is the raw value Supabase returned (or null).
 * No defaults, no Math.random, no hardcoded firmware versions. The atoms know
 * how to render '—' when a field is null.
 */
'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import { createClient } from '@/lib/supabase';
import type { TelemetryRow, DeviceInfo } from './atoms';

interface DeviceSummary {
    /** Internal Supabase device_id (stratolink-N or DevEUI). */
    id: string;
    /** Operator-facing callsign claimed at registration time. */
    callsign: string | null;
    status: 'flying' | 'idle' | 'recovered' | 'lost' | string;
    launchedAt: number | null;
    launchLat: number | null;
    launchLon: number | null;
    /** Epoch-ms timestamp of the most recent uplink for this device, or null. */
    lastContactT: number | null;
    /** Latest position with a valid GPS fix in the last 24h, or null. */
    latestFix: { lat: number; lon: number; alt: number | null; t: number } | null;
}

const FULL_TELEMETRY_COLUMNS =
    'time, lat, lon, altitude_m, battery_voltage, solar_voltage, temperature, pressure, ' +
    'rssi, snr, gps_speed, gps_heading, gps_satellites, mems_accel_x, mems_accel_y, mems_accel_z, ' +
    'velocity_x, velocity_y, ' +
    'uv_index, ambient_lux, acoustic_event, firmware_version, uptime_s, tx_count, hdop, ' +
    'power_mode, sleep_ms, lora_sf, lora_bw, frequency_hz';

function rawToTelemetry(raw: Record<string, any>): TelemetryRow {
    return {
        t: new Date(raw.time).getTime(),
        lat: raw.lat ?? null,
        lon: raw.lon ?? null,
        alt: raw.altitude_m ?? null,
        temp: raw.temperature ?? null,
        pres: raw.pressure ?? null,
        batt: raw.battery_voltage ?? null,
        sol: raw.solar_voltage ?? null,
        rssi: raw.rssi ?? null,
        snr: raw.snr ?? null,
        sats: raw.gps_satellites ?? null,
        lux: raw.ambient_lux ?? null,
        uv: raw.uv_index ?? null,
        spd: raw.gps_speed ?? null,
        hdg: raw.gps_heading ?? null,
        ax: raw.mems_accel_x ?? null,
        ay: raw.mems_accel_y ?? null,
        az: raw.mems_accel_z ?? null,
        vx: raw.velocity_x ?? null,
        vy: raw.velocity_y ?? null,
        firmware_version: raw.firmware_version ?? null,
        uptime_s: raw.uptime_s ?? null,
        tx_count: raw.tx_count ?? null,
        hdop: raw.hdop ?? null,
        power_mode: raw.power_mode ?? null,
        sleep_ms: raw.sleep_ms ?? null,
        lora_sf: raw.lora_sf ?? null,
        lora_bw: raw.lora_bw ?? null,
        frequency_hz: raw.frequency_hz ?? null,
    };
}

/* Per-subsystem freshness — when did this field last update with a real value?
 * Mirrors the FRESHNESS object in the design's components.jsx. */
export interface SubsystemFreshness {
    packet: number | null;
    position: number | null;
    altitude: number | null;
    velocity: number | null;
    battery: number | null;
    solar: number | null;
    temperature: number | null;
    pressure: number | null;
    lux: number | null;
    rssi: number | null;
    imu: number | null;
    snr: number | null;
}

/* Fleet-wide aggregates for the Mission Control top bar. */
export interface FleetMetrics {
    totalDevices: number;
    activeCount: number;
    uplinks24h: number;
    uplinksLastHour: number;
    gpsLockRatePct: number | null;
    noFixCount: number;
    medianRssi: number | null;
    /** Epoch-ms of the very first GPS fix in the last 24h across the fleet. */
    firstFixT: number | null;
    /** Epoch-ms of the very last uplink across the fleet. */
    lastUplinkT: number | null;
}

/* Heuristic alert — derived from real rows, not stored anywhere. */
export interface FleetAlert {
    id: string;
    severity: 'warn' | 'info';
    title: string;
    detail: string;
    deviceId: string | null;
    t: number;
}

export interface UseTelemetryResult {
    /** All registered devices with status + latest contact + latest fix. */
    devices: DeviceSummary[];
    /** The selected device id (defaults to first flying device, or null). */
    selectedId: string | null;
    setSelectedId: (id: string | null) => void;
    /** Last 24h of telemetry rows for the selected device, oldest → newest. */
    rows: TelemetryRow[];
    /** Static device metadata (callsign, launch info, packet count). */
    deviceInfo: DeviceInfo | null;
    /** Per-subsystem last-good-value timestamps for the selected device. */
    freshness: SubsystemFreshness;
    /** Fleet-wide aggregates over the last 24h. */
    fleet: FleetMetrics;
    /** Heuristic alerts derived from the selected-device window. */
    alerts: FleetAlert[];
    /** True until the first fetch completes. */
    loading: boolean;
    /** Last successful fetch wall-clock time (ms epoch). */
    lastFetchedAt: number | null;
    /** Connection state — useful for an "OFFLINE" pill in the chrome. */
    status: 'connecting' | 'connected' | 'disconnected' | 'error';
    /** Force a refetch (not normally needed — auto-polls every 15s). */
    refetch: () => void;
}

const EMPTY_FLEET: FleetMetrics = {
    totalDevices: 0,
    activeCount: 0,
    uplinks24h: 0,
    uplinksLastHour: 0,
    gpsLockRatePct: null,
    noFixCount: 0,
    medianRssi: null,
    firstFixT: null,
    lastUplinkT: null,
};

const EMPTY_FRESHNESS: SubsystemFreshness = {
    packet: null, position: null, altitude: null, velocity: null,
    battery: null, solar: null, temperature: null, pressure: null,
    lux: null, rssi: null, imu: null, snr: null,
};

function computeFreshness(rows: TelemetryRow[]): SubsystemFreshness {
    const f: SubsystemFreshness = { ...EMPTY_FRESHNESS };
    /* Walk newest → oldest and capture the first packet that has a real value
     * for each subsystem. Cheap O(n) since we early-out per field. */
    for (let i = rows.length - 1; i >= 0; i--) {
        const r = rows[i];
        if (f.packet === null) f.packet = r.t;
        if (f.position === null && r.lat !== null && r.lon !== null) f.position = r.t;
        if (f.altitude === null && r.alt !== null) f.altitude = r.t;
        if (f.velocity === null && (r.vx !== null || r.vy !== null || r.spd !== null)) f.velocity = r.t;
        if (f.battery === null && r.batt !== null) f.battery = r.t;
        if (f.solar === null && r.sol !== null) f.solar = r.t;
        if (f.temperature === null && r.temp !== null) f.temperature = r.t;
        if (f.pressure === null && r.pres !== null) f.pressure = r.t;
        if (f.lux === null && (r.lux !== null || r.uv !== null)) f.lux = r.t;
        if (f.rssi === null && r.rssi !== null) f.rssi = r.t;
        if (f.snr === null && r.snr !== null) f.snr = r.t;
        if (f.imu === null && (r.ax !== null || r.ay !== null || r.az !== null)) f.imu = r.t;
    }
    return f;
}

function median(values: number[]): number | null {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const m = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
}

function deriveAlerts(rows: TelemetryRow[], deviceId: string | null): FleetAlert[] {
    if (!rows.length) return [];
    const out: FleetAlert[] = [];

    /* GPS dropout — N consecutive rows without a fix. */
    let dropStart: number | null = null;
    let dropCount = 0;
    rows.forEach((r) => {
        if (r.lat === null || r.lon === null) {
            if (dropStart === null) dropStart = r.t;
            dropCount += 1;
        } else {
            if (dropStart !== null && dropCount >= 5) {
                out.push({
                    id: `gps-${dropStart}`,
                    severity: 'warn',
                    title: 'GPS DROPOUT',
                    detail: `${dropCount} consecutive packets without GPS fix`,
                    deviceId,
                    t: dropStart,
                });
            }
            dropStart = null;
            dropCount = 0;
        }
    });
    if (dropStart !== null && dropCount >= 5) {
        out.push({
            id: `gps-${dropStart}`,
            severity: 'warn',
            title: 'GPS DROPOUT (ONGOING)',
            detail: `${dropCount} consecutive packets without GPS fix`,
            deviceId,
            t: dropStart,
        });
    }

    /* Battery low — latest reading below 3.5V. */
    const latestBatt = [...rows].reverse().find(r => r.batt !== null);
    if (latestBatt && latestBatt.batt !== null && latestBatt.batt < 3.5) {
        out.push({
            id: `batt-low-${latestBatt.t}`,
            severity: 'warn',
            title: 'BATTERY LOW',
            detail: `${latestBatt.batt.toFixed(2)}V — below 3.5V threshold`,
            deviceId,
            t: latestBatt.t,
        });
    }

    /* Battery recovery — solar crossed back above 4.5V after being below. */
    for (let i = 1; i < rows.length; i++) {
        const prev = rows[i - 1].sol;
        const cur = rows[i].sol;
        if (prev !== null && cur !== null && prev < 4.5 && cur >= 4.5) {
            out.push({
                id: `solar-rec-${rows[i].t}`,
                severity: 'info',
                title: 'BATTERY RECOVERY',
                detail: 'Solar voltage crossed 4.5V threshold',
                deviceId,
                t: rows[i].t,
            });
            break;
        }
    }

    /* Most recent first, cap at 5 to keep the panel from exploding. */
    return out.sort((a, b) => b.t - a.t).slice(0, 5);
}

export function useTelemetry({ initialSelectedId = null }: { initialSelectedId?: string | null } = {}): UseTelemetryResult {
    const [devices, setDevices] = useState<DeviceSummary[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(initialSelectedId);
    const [rows, setRows] = useState<TelemetryRow[]>([]);
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
    const [fleet, setFleet] = useState<FleetMetrics>(EMPTY_FLEET);
    const [loading, setLoading] = useState(true);
    const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);
    const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('connecting');
    const [tick, setTick] = useState(0);

    const refetch = useCallback(() => setTick(t => t + 1), []);

    /* Fetch the device list + latest fix per device. Auto-selects the first
     * flying device if nothing is selected yet. */
    useEffect(() => {
        let cancelled = false;
        async function load() {
            const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!url || url.includes('your_supabase') || url === '') {
                if (!cancelled) {
                    setStatus('disconnected');
                    setLoading(false);
                }
                return;
            }
            try {
                const supabase = createClient();
                const { data: rawDevices, error: devErr } = await supabase
                    .from('devices')
                    .select('device_id, launcher_name, status, launch_lat, launch_lon, launched_at')
                    .order('device_id', { ascending: true });
                if (devErr) throw devErr;

                const ids = (rawDevices ?? []).map((d: any) => d.device_id);
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

                /* Latest contact per device — even sensor-only NOGPS rows count. */
                const { data: contacts } = ids.length
                    ? await supabase
                          .from('telemetry')
                          .select('device_id, time')
                          .in('device_id', ids)
                          .gte('time', oneDayAgo)
                          .order('time', { ascending: false })
                    : { data: [] as Array<{ device_id: string; time: string }> };

                const latestContactByDevice = new Map<string, number>();
                (contacts ?? []).forEach((row: any) => {
                    const t = new Date(row.time).getTime();
                    const prev = latestContactByDevice.get(row.device_id);
                    if (!prev || t > prev) latestContactByDevice.set(row.device_id, t);
                });

                /* Latest GPS-fixed position per device. */
                const { data: fixes } = ids.length
                    ? await supabase
                          .from('telemetry')
                          .select('device_id, lat, lon, altitude_m, time')
                          .in('device_id', ids)
                          .gte('time', oneDayAgo)
                          .not('lat', 'is', null)
                          .not('lon', 'is', null)
                          .order('time', { ascending: false })
                    : { data: [] as any[] };

                const latestFixByDevice = new Map<string, DeviceSummary['latestFix']>();
                (fixes ?? []).forEach((row: any) => {
                    if (latestFixByDevice.has(row.device_id)) return;
                    latestFixByDevice.set(row.device_id, {
                        lat: row.lat,
                        lon: row.lon,
                        alt: row.altitude_m,
                        t: new Date(row.time).getTime(),
                    });
                });

                const summaries: DeviceSummary[] = (rawDevices ?? []).map((d: any) => ({
                    id: d.device_id,
                    callsign: d.launcher_name ?? null,
                    status: d.status,
                    launchedAt: d.launched_at ? new Date(d.launched_at).getTime() : null,
                    launchLat: d.launch_lat ?? null,
                    launchLon: d.launch_lon ?? null,
                    lastContactT: latestContactByDevice.get(d.device_id) ?? null,
                    latestFix: latestFixByDevice.get(d.device_id) ?? null,
                }));

                if (cancelled) return;
                setDevices(summaries);
                setStatus('connected');
                setLoading(false);
                setLastFetchedAt(Date.now());

                if (selectedId === null && summaries.length > 0) {
                    /* Prefer flying devices, then anything with recent contact, else first. */
                    const flying = summaries.find(s => s.status === 'flying');
                    const recent = summaries.find(s => s.lastContactT !== null);
                    setSelectedId((flying ?? recent ?? summaries[0]).id);
                }

                /* Fleet-wide aggregates: count uplinks, GPS lock rate, median RSSI.
                 * One small extra query — pull the lightweight columns only. */
                if (ids.length) {
                    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                    const { data: aggRows } = await supabase
                        .from('telemetry')
                        .select('device_id, time, lat, lon, rssi')
                        .in('device_id', ids)
                        .gte('time', oneDayAgo);

                    const safe: Array<{ device_id: string; time: string; lat: number | null; lon: number | null; rssi: number | null }> =
                        (aggRows ?? []) as any;
                    const total = safe.length;
                    const withFix = safe.filter(r => r.lat !== null && r.lon !== null).length;
                    const noFix = total - withFix;
                    const lastHour = safe.filter(r => r.time >= oneHourAgo).length;
                    const rssiVals = safe
                        .map(r => r.rssi)
                        .filter((v): v is number => v !== null && Number.isFinite(v));
                    const med = median(rssiVals);
                    const fixTimes = safe
                        .filter(r => r.lat !== null && r.lon !== null)
                        .map(r => new Date(r.time).getTime());
                    const allTimes = safe.map(r => new Date(r.time).getTime());
                    const activeDeviceIds = new Set(safe.map(r => r.device_id));

                    if (!cancelled) {
                        setFleet({
                            totalDevices: summaries.length,
                            activeCount: activeDeviceIds.size,
                            uplinks24h: total,
                            uplinksLastHour: lastHour,
                            gpsLockRatePct: total > 0 ? (withFix / total) * 100 : null,
                            noFixCount: noFix,
                            medianRssi: med,
                            firstFixT: fixTimes.length ? Math.min(...fixTimes) : null,
                            lastUplinkT: allTimes.length ? Math.max(...allTimes) : null,
                        });
                    }
                } else if (!cancelled) {
                    setFleet({ ...EMPTY_FLEET, totalDevices: summaries.length });
                }
            } catch (e) {
                console.debug('useTelemetry devices error', e);
                if (!cancelled) {
                    setStatus('error');
                    setLoading(false);
                }
            }
        }
        load();
        const interval = setInterval(load, 30_000);
        return () => { cancelled = true; clearInterval(interval); };
    }, [tick, selectedId]);

    /* Fetch the full last-24h row set for the selected device. Polls every 15s. */
    useEffect(() => {
        if (!selectedId) {
            setRows([]);
            setDeviceInfo(null);
            return;
        }
        let cancelled = false;
        async function load() {
            try {
                const supabase = createClient();
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                const { data, error } = await supabase
                    .from('telemetry')
                    .select(FULL_TELEMETRY_COLUMNS)
                    .eq('device_id', selectedId)
                    .gte('time', oneDayAgo)
                    .order('time', { ascending: true });
                if (error) throw error;
                if (cancelled) return;
                const next = (data ?? []).map(rawToTelemetry);
                setRows(next);

                const summary = devices.find(d => d.id === selectedId);
                /* Pull the most recent firmware_version that was actually
                 * reported. If the firmware never sends it, this stays null
                 * and the UI displays '—' — never a placeholder. */
                const latestWithFw = [...next].reverse().find(r => r.firmware_version);
                const latestRow = next[next.length - 1];
                setDeviceInfo({
                    id: selectedId!,
                    firmware: latestWithFw?.firmware_version ?? null,
                    launched_by: summary?.callsign ?? null,
                    launched_at: summary?.launchedAt ?? null,
                    freq_mhz: latestRow?.frequency_hz ? latestRow.frequency_hz / 1_000_000 : null,
                    sf: latestRow?.lora_sf && latestRow?.lora_bw
                        ? `SF${latestRow.lora_sf}BW${Math.round(latestRow.lora_bw / 1000)}`
                        : null,
                    packet_count: next.length,
                });
                setLastFetchedAt(Date.now());
            } catch (e) {
                console.debug('useTelemetry rows error', e);
            }
        }
        load();
        const interval = setInterval(load, 15_000);
        return () => { cancelled = true; clearInterval(interval); };
    }, [selectedId, devices, tick]);

    const freshness = useMemo(() => computeFreshness(rows), [rows]);
    const alerts = useMemo(() => deriveAlerts(rows, selectedId), [rows, selectedId]);

    return {
        devices, selectedId, setSelectedId,
        rows, deviceInfo, freshness, fleet, alerts,
        loading, lastFetchedAt, status, refetch,
    };
}

export type { DeviceSummary };
