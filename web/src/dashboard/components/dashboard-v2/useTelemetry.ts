import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { isHiddenAliasDevice } from '@/lib/devices/aliases';
import { createClient } from '@/lib/supabase';
import { fetchTelemetryMerged } from '@/lib/telemetry/fetchMergedTelemetry';
import { rawToTelemetry } from '@/lib/telemetry/mapTelemetryRow';
import { createHistoryLoader, type HistoryWindow } from '@/lib/telemetry/historyCache';
import { telemetrySinceMs } from '@/lib/telemetry/missionWindow';
import { shouldPollTelemetry } from '@/lib/telemetry/fleetSummary';
import type { TelemetryRow } from './atoms';

interface DeviceSummary {
    ownerGithub?: string;
    ownerId?: string;
    official?: boolean;
    connectionStatus?: 'pending' | 'connected';
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
    /** Latest position with a valid GPS fix since launch, or null. */
    latestFix: { lat: number; lon: number; alt: number | null; t: number } | null;
}

const FULL_TELEMETRY_COLUMNS =
    'time, lat, lon, altitude_m, battery_voltage, solar_voltage, temperature, pressure, ' +
    'rssi, snr, gps_speed, gps_heading, gps_satellites, mems_accel_x, mems_accel_y, mems_accel_z, ' +
    'velocity_x, velocity_y, ' +
    'uv_index, ambient_lux, acoustic_event, firmware_version, uptime_s, tx_count, hdop, ' +
    'power_mode, sleep_ms, lora_sf, lora_bw, frequency_hz, gateways';


const TELEMETRY_POLL_MS = 60_000;

function pollWhileVisible(fn: () => void, ms: number): () => void {
    if (typeof document === 'undefined') {                 // SSR / non-browser
        const id = setInterval(fn, ms);
        return () => clearInterval(id);
    }
    const id = setInterval(() => { if (!document.hidden) fn(); }, ms);
    const onVisible = () => { if (!document.hidden) fn(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', onVisible); };
}


let cachedDevices: DeviceSummary[] | null = null;
const cachedRowsByDevice = new Map<string, TelemetryRow[]>();
const missionHistory = createHistoryLoader(cachedRowsByDevice, async (deviceId, since) => {
    const raw = await fetchTelemetryMerged(createClient(), {
        deviceId,
        since: new Date(since).toISOString(),
        columns: FULL_TELEMETRY_COLUMNS,
    });
    return raw.map(rawToTelemetry);
});

function historyWindow(device: Pick<DeviceSummary, 'id' | 'status' | 'launchedAt'>): HistoryWindow {
    return {
        deviceId: device.id,
        since: telemetrySinceMs(device, Date.now(), { fullHistory: true }),
    };
}

export interface UseFleetHistoryResult {
    rowsByDevice: Record<string, TelemetryRow[]>;
    loading: boolean;
    error: string | null;
}

/** The overview loads missions independently so one failed device cannot hide the others. */
export function useFleetHistory(devices: DeviceSummary[], enabled: boolean): UseFleetHistoryResult {
    const devicesRef = useRef(devices);
    devicesRef.current = devices;
    const deviceKey = JSON.stringify(devices
        .filter(device => !isHiddenAliasDevice(device.id))
        .map(device => [device.id, device.launchedAt, device.status])
        .sort((a, b) => String(a[0]).localeCompare(String(b[0]))));
    const [rowsByDevice, setRowsByDevice] = useState<Record<string, TelemetryRow[]>>(() =>
        Object.fromEntries(devices
            .filter(device => !isHiddenAliasDevice(device.id) && cachedRowsByDevice.has(device.id))
            .map(device => [device.id, cachedRowsByDevice.get(device.id)!])),
    );
    const [loading, setLoading] = useState(enabled && devices.some(device => !cachedRowsByDevice.has(device.id)));
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!enabled) {
            setLoading(false);
            return;
        }
        let cancelled = false;
        let running = false;
        let publishTimer: ReturnType<typeof setTimeout> | undefined;
        const windows = devicesRef.current
            .filter(device => !isHiddenAliasDevice(device.id))
            .map(device => ({ ...historyWindow(device), poll: shouldPollTelemetry(device.status) }));
        const snapshot = () => Object.fromEntries(windows
            .filter(window => cachedRowsByDevice.has(window.deviceId))
            .map(window => [window.deviceId, cachedRowsByDevice.get(window.deviceId)!]));

        setRowsByDevice(snapshot());
        setLoading(windows.some(window => missionHistory.peek(window) === undefined));
        setError(null);

        async function refresh(initial = false) {
            if (cancelled || running || document.hidden) return;
            running = true;
            const results = await Promise.allSettled(windows.map(async window => {
                await missionHistory.load(window, { refresh: initial || window.poll });
                if (!cancelled && publishTimer === undefined) publishTimer = setTimeout(() => {
                    publishTimer = undefined;
                    if (!cancelled) setRowsByDevice(snapshot());
                }, 50);
            }));
            running = false;
            if (cancelled) return;
            clearTimeout(publishTimer);
            publishTimer = undefined;
            setRowsByDevice(snapshot());
            setLoading(false);
            const failures = results.flatMap((result, index) => {
                if (result.status === 'fulfilled') return [];
                const reason: unknown = result.reason;
                const message = typeof reason === 'object' && reason !== null && 'message' in reason
                    ? String(reason.message)
                    : 'Unable to load history';
                return [`${windows[index].deviceId}: ${message}`];
            });
            setError(failures.length ? failures.join('; ') : null);
        }

        void refresh(true);
        const stop = pollWhileVisible(() => { void refresh(); }, TELEMETRY_POLL_MS);
        return () => { cancelled = true; clearTimeout(publishTimer); stop(); };
    }, [enabled, deviceKey]);

    return { rowsByDevice, loading, error };
}


export function useTelemetry({ initialSelectedId = null }: { initialSelectedId?: string | null } = {}) {
    const [devices, setDevices] = useState<DeviceSummary[]>(() => cachedDevices ?? []);
    const [selectedId, updateSelectedId] = useState<string | null>(initialSelectedId);
    const [rows, setRows] = useState<TelemetryRow[]>(
        () => (initialSelectedId ? cachedRowsByDevice.get(initialSelectedId) : undefined) ?? [],
    );
    const [loading, setLoading] = useState(cachedDevices === null);
    const [tick, setTick] = useState(0);
    const refetch = useCallback(() => setTick(t => t + 1), []);
    const setSelectedId = useCallback((id: string | null) => {
        updateSelectedId(id);
        setRows(id ? cachedRowsByDevice.get(id) ?? [] : []);
    }, []);

    // Card selection reuses the registry and history instead of querying the fleet again.
    useEffect(() => {
        let cancelled = false;
        async function load() {
            try {
                const { data, error } = await createClient()
                    .from('devices')
                    .select('device_id, launcher_name, status, launch_lat, launch_lon, launched_at, display_name, owner_github, official, connection_status')
                    .order('device_id', { ascending: true });
                if (error) throw error;
                if (cancelled) return;
                const summaries: DeviceSummary[] = (data ?? [])
                    .filter(device => !isHiddenAliasDevice(device.device_id))
                    .map(device => ({
                        id: device.device_id,
                        callsign: device.display_name ?? device.launcher_name ?? null,
                        official: device.official === true,
                        connectionStatus: device.connection_status,
                        ownerGithub: device.owner_github ?? undefined,
                        status: device.status,
                        launchedAt: device.launched_at ? new Date(device.launched_at).getTime() : null,
                        launchLat: device.launch_lat ?? null,
                        launchLon: device.launch_lon ?? null,
                        lastContactT: null,
                        latestFix: null,
                    }));
                cachedDevices = summaries;
                setDevices(summaries);
            } catch (error) {
                console.debug('useTelemetry devices error', error);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        void load();
        const stop = pollWhileVisible(() => { void load(); }, TELEMETRY_POLL_MS);
        return () => { cancelled = true; stop(); };
    }, [tick]);

    const selected = useMemo(() => devices.find(device => device.id === selectedId), [devices, selectedId]);
    const selectedStatus = selected?.status;
    const launchedAt = selected?.launchedAt ?? null;
    const known = selected !== undefined;
    useEffect(() => {
        if (!selectedId) { setRows([]); return; }
        const id = selectedId;
        setRows(cachedRowsByDevice.get(id) ?? []);
        if (!known) return;
        let cancelled = false;
        const window = historyWindow({ id, status: selectedStatus ?? '', launchedAt });
        const refresh = async () => {
            try {
                const next = await missionHistory.load(window, { refresh: true });
                if (!cancelled) setRows(next);
            } catch (error) { console.debug('useTelemetry rows error', error); }
        };
        void refresh();
        const stop = shouldPollTelemetry(selectedStatus ?? '')
            ? pollWhileVisible(() => { void refresh(); }, TELEMETRY_POLL_MS)
            : () => {};
        return () => { cancelled = true; stop(); };
    }, [selectedId, known, selectedStatus, launchedAt, tick]);

    return { devices, selectedId, setSelectedId, rows, loading, refetch };
}

export type { DeviceSummary };
