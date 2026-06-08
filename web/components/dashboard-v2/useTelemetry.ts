/**
 * useTelemetry — bridge between Supabase telemetry rows and the v2 dashboard
 * atoms. Returns rows in the design's data vocabulary so atoms drop in 1:1.
 *
 * Strict rule: every value here is the raw value Supabase returned (or null).
 * No defaults, no Math.random, no hardcoded firmware versions. The atoms know
 * how to render '—' when a field is null.
 */
'use client';

import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { expandFleetDeviceIdsForTelemetry, isHiddenAliasDevice } from '@/lib/devices/aliases';
import { createClient } from '@/lib/supabase';
import {
    canonicalDeviceId,
    fetchFleetTelemetryLight,
    fetchLatestContactMs,
    fetchLatestGpsFix,
    fetchTelemetryMerged,
} from '@/lib/telemetry/fetchMergedTelemetry';
import { rawToTelemetry } from '@/lib/telemetry/mapTelemetryRow';
import {
    fleetTelemetrySinceIso,
    telemetrySinceIso,
    type MissionWindowDevice,
} from '@/lib/telemetry/missionWindow';
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
    'power_mode, sleep_ms, lora_sf, lora_bw, frequency_hz, gateways';

/* Poll cadences. These were 30 s / 15 s, which — across left-open background tabs —
 * generated ~14k Supabase requests/day PER tab (most of our egress). Longer intervals
 * + pausing while the tab is hidden cut that ~20–50×. A flying balloon reports every
 * few minutes anyway, so a minute of latency costs nothing. */
const DEVICE_POLL_MS = 90_000;
const TELEMETRY_POLL_MS = 60_000;

/** setInterval that PAUSES while the tab is backgrounded (`document.hidden`) and fires
 *  once immediately when it becomes visible again — so a left-open background tab stops
 *  hammering Supabase, while a focused tab still feels live. Returns a cleanup fn. */
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

/* ──────────────────────────────────────────────────────────────
 * Cross-mount cache. Each dashboard tab is its own route, so switching
 * tabs unmounts this hook and remounts it on the next screen. Without a
 * cache every switch starts from an empty "loading" state and re-queries
 * Supabase before anything renders — which is what made tab changes feel
 * slow. We keep the last good result at module scope so a remount renders
 * instantly, then the effects below still re-fetch to revalidate.
 * ────────────────────────────────────────────────────────────── */
let cachedDevices: DeviceSummary[] | null = null;
let cachedFleet: FleetMetrics | null = null;
const cachedRowsByDevice = new Map<string, TelemetryRow[]>();
const cachedInfoByDevice = new Map<string, DeviceInfo>();

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
    const [devices, setDevices] = useState<DeviceSummary[]>(() => cachedDevices ?? []);
    const [selectedId, setSelectedId] = useState<string | null>(initialSelectedId);
    const [rows, setRows] = useState<TelemetryRow[]>(
        () => (initialSelectedId ? cachedRowsByDevice.get(initialSelectedId) : undefined) ?? [],
    );
    const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(
        () => (initialSelectedId ? cachedInfoByDevice.get(initialSelectedId) : undefined) ?? null,
    );
    const [fleet, setFleet] = useState<FleetMetrics>(() => cachedFleet ?? EMPTY_FLEET);
    const [loading, setLoading] = useState(cachedDevices === null);
    const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);
    const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>(
        cachedDevices !== null ? 'connected' : 'connecting',
    );
    const [tick, setTick] = useState(0);

    const refetch = useCallback(() => setTick(t => t + 1), []);

    /* Latest devices, readable inside the polling closures without making the
     * mission-rows effect depend on the array identity (the fleet poll rebuilds
     * `devices` every 30s — depending on it would re-trigger a full-history
     * reload that often, which is most of our DB egress). */
    const devicesRef = useRef(devices);
    devicesRef.current = devices;

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

                const fleetDevices = (rawDevices ?? []).filter(
                    (d: { device_id: string }) => !isHiddenAliasDevice(d.device_id),
                );
                const ids = fleetDevices.map((d: { device_id: string }) => d.device_id);
                const telemetryIds = expandFleetDeviceIdsForTelemetry(ids);
                const missionDevices: MissionWindowDevice[] = fleetDevices.map((d: any) => ({
                    status: d.status,
                    launchedAt: d.launched_at ? new Date(d.launched_at).getTime() : null,
                }));
                const fleetSince = fleetTelemetrySinceIso(missionDevices);

                /* Per-device latest contact + fix (canonical + alias ids merged). */
                const summaries: DeviceSummary[] = await Promise.all(
                    fleetDevices.map(async (d: any) => {
                        const launchedAt = d.launched_at ? new Date(d.launched_at).getTime() : null;
                        const since = telemetrySinceIso({
                            status: d.status,
                            launchedAt,
                        });
                        const [lastContactT, latestFix] = await Promise.all([
                            fetchLatestContactMs(supabase, d.device_id, since),
                            fetchLatestGpsFix(supabase, d.device_id, since),
                        ]);
                        return {
                            id: d.device_id,
                            callsign: d.launcher_name ?? null,
                            status: d.status,
                            launchedAt,
                            launchLat: d.launch_lat ?? null,
                            launchLon: d.launch_lon ?? null,
                            lastContactT,
                            latestFix,
                        };
                    }),
                );

                if (cancelled) return;
                cachedDevices = summaries;
                setDevices(summaries);
                setStatus('connected');
                setLoading(false);
                setLastFetchedAt(Date.now());

                if (selectedId === null && summaries.length > 0) {
                    /* Pick the flying device that's actually transmitting. Sort by most-recent-
                     * contact desc so a stale 'flying' row from an old test launch never wins
                     * over the device that's currently in the air. Falls back through:
                     *   1. flying + has recent contact (the right answer 99% of the time)
                     *   2. any device with recent contact (a still-talking device that wasn't
                     *      tagged 'flying' yet — better than picking something silent)
                     *   3. any flying device (no contact at all — at least it's the "intended" one)
                     *   4. the first device in the list (nothing to go on, anything is fine) */
                    const byRecency = (a: DeviceSummary, b: DeviceSummary) =>
                        (b.lastContactT ?? 0) - (a.lastContactT ?? 0);
                    const flyingActive = [...summaries]
                        .filter(s => s.status === 'flying' && s.lastContactT !== null)
                        .sort(byRecency)[0];
                    const anyActive = [...summaries]
                        .filter(s => s.lastContactT !== null)
                        .sort(byRecency)[0];
                    const anyFlying = summaries.find(s => s.status === 'flying');
                    setSelectedId((flyingActive ?? anyActive ?? anyFlying ?? summaries[0]).id);
                }

                /* Fleet-wide aggregates: count uplinks, GPS lock rate, median RSSI.
                 * One small extra query — pull the lightweight columns only. */
                if (telemetryIds.length) {
                    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                    const safe = await fetchFleetTelemetryLight(supabase, telemetryIds, fleetSince);
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
                    const activeDeviceIds = new Set(
                        safe.map(r => canonicalDeviceId(r.device_id)).filter(id => ids.includes(id)),
                    );

                    if (!cancelled) {
                        const fm: FleetMetrics = {
                            totalDevices: summaries.length,
                            activeCount: activeDeviceIds.size,
                            uplinks24h: total,
                            uplinksLastHour: lastHour,
                            gpsLockRatePct: total > 0 ? (withFix / total) * 100 : null,
                            noFixCount: noFix,
                            medianRssi: med,
                            firstFixT: fixTimes.length ? Math.min(...fixTimes) : null,
                            lastUplinkT: allTimes.length ? Math.max(...allTimes) : null,
                        };
                        cachedFleet = fm;
                        setFleet(fm);
                    }
                } else if (!cancelled) {
                    const fm: FleetMetrics = { ...EMPTY_FLEET, totalDevices: summaries.length };
                    cachedFleet = fm;
                    setFleet(fm);
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
        const stop = pollWhileVisible(load, DEVICE_POLL_MS);
        return () => { cancelled = true; stop(); };
    }, [tick, selectedId]);

    /* Full mission row set for the selected device. Loaded in full once (since
     * launch), then refreshed INCREMENTALLY — each poll fetches only rows newer
     * than the last one we hold and appends them. Re-downloading the entire
     * flight every 15s (the old behaviour) was the bulk of our Supabase egress:
     * a 16-day flight is multiple MB, and at 4 polls/min per open tab that runs
     * to hundreds of MB/hour. A landed/retired flight never gains rows, so it's
     * loaded once and not polled at all. */
    const selSummary = useMemo(
        () => devices.find(d => d.id === selectedId) ?? null,
        [devices, selectedId],
    );
    /* Primitive deps so the effect re-runs on a real device/status/launch change,
     * not on every fleet-poll rebuild of the `devices` array. */
    const selStatus = selSummary?.status;
    const selLaunchedAt = selSummary?.launchedAt ?? null;
    useEffect(() => {
        if (!selectedId) {
            setRows([]);
            setDeviceInfo(null);
            return;
        }
        const sel = selectedId;
        let cancelled = false;

        /* Recompute device metadata from the merged set and publish rows. */
        const commit = (next: TelemetryRow[]) => {
            cachedRowsByDevice.set(sel, next);
            setRows(next);
            const summary = devicesRef.current.find(d => d.id === sel);
            /* Most recent firmware_version actually reported; '—' if never sent. */
            const latestWithFw = [...next].reverse().find(r => r.firmware_version);
            const latestRow = next[next.length - 1];
            const info: DeviceInfo = {
                id: sel,
                firmware: latestWithFw?.firmware_version ?? null,
                launched_by: summary?.callsign ?? null,
                launched_at: summary?.launchedAt ?? null,
                freq_mhz: latestRow?.frequency_hz ? latestRow.frequency_hz / 1_000_000 : null,
                sf: latestRow?.lora_sf && latestRow?.lora_bw
                    ? `SF${latestRow.lora_sf}BW${Math.round(latestRow.lora_bw / 1000)}`
                    : null,
                packet_count: next.length,
            };
            cachedInfoByDevice.set(sel, info);
            setDeviceInfo(info);
            setLastFetchedAt(Date.now());
        };

        /* fullHistory: the operator selected this device to inspect it, so load
         * its entire flight since launch — including landed / retired balloons,
         * which otherwise only get a rolling 24h window and would show no track. */
        const fullLoad = async () => {
            const supabase = createClient();
            const since = telemetrySinceIso(
                { status: selStatus, launchedAt: selLaunchedAt },
                Date.now(),
                { fullHistory: true },
            );
            const raw = await fetchTelemetryMerged(supabase, {
                deviceId: sel, since, columns: FULL_TELEMETRY_COLUMNS,
            });
            if (cancelled) return;
            commit(raw.map(rawToTelemetry));
        };

        /* Fetch only rows newer than the latest we hold and append them. `gte`
         * re-includes the boundary row, which we drop with `t > lastT`. */
        const pollIncrement = async () => {
            const have = cachedRowsByDevice.get(sel) ?? [];
            if (!have.length) return fullLoad();
            const lastT = have[have.length - 1].t;
            const supabase = createClient();
            const raw = await fetchTelemetryMerged(supabase, {
                deviceId: sel,
                since: new Date(lastT).toISOString(),
                columns: FULL_TELEMETRY_COLUMNS,
            });
            if (cancelled) return;
            const appended = raw.map(rawToTelemetry).filter(r => r.t > lastT);
            if (!appended.length) { setLastFetchedAt(Date.now()); return; }
            commit(have.concat(appended));
        };

        fullLoad().catch(e => console.debug('useTelemetry rows error', e));

        /* Only a flying flight gains new packets — don't poll static history. */
        if (selStatus !== 'flying') {
            return () => { cancelled = true; };
        }
        const stop = pollWhileVisible(
            () => pollIncrement().catch(e => console.debug('useTelemetry poll error', e)),
            TELEMETRY_POLL_MS,
        );
        return () => { cancelled = true; stop(); };
    }, [selectedId, selStatus, selLaunchedAt, tick]);

    const freshness = useMemo(() => computeFreshness(rows), [rows]);
    const alerts = useMemo(() => deriveAlerts(rows, selectedId), [rows, selectedId]);

    return {
        devices, selectedId, setSelectedId,
        rows, deviceInfo, freshness, fleet, alerts,
        loading, lastFetchedAt, status, refetch,
    };
}

export type { DeviceSummary };
