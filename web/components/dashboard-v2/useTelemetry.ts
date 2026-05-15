/**
 * useTelemetry — bridge between Supabase telemetry rows and the v2 dashboard
 * atoms. Returns rows in the design's data vocabulary so atoms drop in 1:1.
 *
 * Strict rule: every value here is the raw value Supabase returned (or null).
 * No defaults, no Math.random, no hardcoded firmware versions. The atoms know
 * how to render '—' when a field is null.
 */
'use client';

import { useEffect, useState, useCallback } from 'react';
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
    /** True until the first fetch completes. */
    loading: boolean;
    /** Last successful fetch wall-clock time (ms epoch). */
    lastFetchedAt: number | null;
    /** Connection state — useful for an "OFFLINE" pill in the chrome. */
    status: 'connecting' | 'connected' | 'disconnected' | 'error';
    /** Force a refetch (not normally needed — auto-polls every 15s). */
    refetch: () => void;
}

export function useTelemetry({ initialSelectedId = null }: { initialSelectedId?: string | null } = {}): UseTelemetryResult {
    const [devices, setDevices] = useState<DeviceSummary[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(initialSelectedId);
    const [rows, setRows] = useState<TelemetryRow[]>([]);
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
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

    return { devices, selectedId, setSelectedId, rows, deviceInfo, loading, lastFetchedAt, status, refetch };
}

export type { DeviceSummary };
