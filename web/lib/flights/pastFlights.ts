/**
 * Past-flights data layer for the dashboard-v2 Mission Archive.
 *
 * A "past flight" is a launched device whose mission is over (status
 * `landed` or `retired`), pulled from Supabase, plus curated fallback
 * flights baked into the app so the archive always has something to show
 * before any real flights complete.
 *
 * Strict rule (same as useTelemetry): every value is a real Supabase value,
 * a real curated value, or null. No placeholders, no Math.random.
 */
'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { altitudeFromPressureHpa } from '@/lib/atmosphere/isa';
import { FLIGHT_REPORTS } from './registry';
import { BAJA_RUN_FLIGHT } from './baja-run-data';
import type { FlightSample } from './types';
import type { TelemetryRow } from '@/components/dashboard-v2/atoms';

/** Device statuses that mean "the mission is over". */
const PAST_STATUSES = ['landed', 'retired'];

/** Safety cap so a single flight query never pulls unbounded history. */
const MAX_MISSION_MS = 30 * 24 * 60 * 60 * 1000;
/** Row ceiling for a single flight's full-window fetch. */
const FLIGHT_ROW_LIMIT = 5000;

const FULL_TELEMETRY_COLUMNS =
    'time, lat, lon, altitude_m, battery_voltage, solar_voltage, temperature, pressure, ' +
    'rssi, snr, gps_speed, gps_heading, gps_satellites, mems_accel_x, mems_accel_y, mems_accel_z, ' +
    'velocity_x, velocity_y, ' +
    'uv_index, ambient_lux, acoustic_event, firmware_version, uptime_s, tx_count, hdop, ' +
    'power_mode, sleep_ms, lora_sf, lora_bw, frequency_hz, gateways';

/* ──────────────────────────────────────────────────────────────
 * Types
 * ────────────────────────────────────────────────────────────── */
export interface PastFlightSummary {
    /** Routing id — a Supabase device_id or a curated slug. */
    id: string;
    source: 'db' | 'curated';
    /** Operator-facing name shown first; falls back to id in the UI. */
    callsign: string | null;
    /** Curated flights carry an editorial title/subtitle; DB flights don't. */
    title: string | null;
    subtitle: string | null;
    deviceId: string;
    status: string;
    launchedAtMs: number | null;
    endedAtMs: number | null;
    durationMs: number | null;
    peakAltM: number | null;
    distanceKm: number | null;
    minTempC: number | null;
    fixCount: number;
    rowCount: number;
    launchCoords: string | null;
    comms: string | null;
}

export interface FlightReplayMeta {
    id: string;
    source: 'db' | 'curated';
    callsign: string | null;
    title: string | null;
    subtitle: string | null;
    deviceId: string;
    status: string;
    launchedAtMs: number | null;
    endedAtMs: number | null;
    comms: string | null;
    firmware: string | null;
}

export type DataStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

/* ──────────────────────────────────────────────────────────────
 * Curated flights — the fallback archive. Each ties a registry entry
 * (display metadata + KPIs) to its telemetry samples and a launch epoch
 * so the samples' minute offsets resolve to real timestamps.
 * ────────────────────────────────────────────────────────────── */
interface CuratedSource {
    slug: string;
    launchMs: number;
    samples: FlightSample[];
}

const CURATED_SOURCES: CuratedSource[] = [
    {
        slug: 'baja-run',
        /* 17 May 2026, 15:55 UTC — matches registry launchedAtUtc. */
        launchMs: Date.UTC(2026, 4, 17, 15, 55, 0),
        samples: BAJA_RUN_FLIGHT,
    },
];

export function isCuratedFlight(id: string): boolean {
    return CURATED_SOURCES.some((c) => c.slug === id);
}

/** Convert curated FlightSample[] into the dashboard's TelemetryRow shape.
 *  Curated samples only carry GPS/altitude/temp/pressure — power, RF and IMU
 *  fields are null and render as '—', exactly like a real packet that omitted
 *  them. */
export function curatedToRows(samples: FlightSample[], launchMs: number): TelemetryRow[] {
    return samples.map((s) => ({
        t: launchMs + s.mins * 60_000,
        lat: s.lat,
        lon: s.lon,
        alt: s.alt_gps,
        temp: s.temp,
        pres: s.pres,
        /* Prefer the curated pressure-altitude; fall back to ISA if absent. */
        presAlt: s.alt_p ?? altitudeFromPressureHpa(s.pres),
        batt: null,
        sol: null,
        rssi: null,
        snr: null,
        sats: null,
        lux: null,
        uv: null,
        spd: null,
        hdg: null,
        ax: null,
        ay: null,
        az: null,
        vx: null,
        vy: null,
        firmware_version: null,
        uptime_s: null,
        tx_count: null,
        hdop: null,
        power_mode: null,
        sleep_ms: null,
        lora_sf: null,
        lora_bw: null,
        frequency_hz: null,
        gateways: null,
    }));
}

/* ──────────────────────────────────────────────────────────────
 * Stats helpers
 * ────────────────────────────────────────────────────────────── */
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

interface TrackStats {
    peakAltM: number | null;
    minTempC: number | null;
    distanceKm: number;
    fixCount: number;
    rowCount: number;
    firstT: number | null;
    lastT: number | null;
}

interface StatRow {
    t: number;
    lat: number | null;
    lon: number | null;
    alt: number | null;
    temp: number | null;
}

function computeTrackStats(rows: StatRow[]): TrackStats {
    let distanceKm = 0;
    let prev: StatRow | null = null;
    let peakAltM: number | null = null;
    let minTempC: number | null = null;
    let fixCount = 0;
    let firstT: number | null = null;
    let lastT: number | null = null;

    for (const r of rows) {
        if (firstT === null || r.t < firstT) firstT = r.t;
        if (lastT === null || r.t > lastT) lastT = r.t;
        if (r.alt !== null && Number.isFinite(r.alt)) {
            peakAltM = peakAltM === null ? r.alt : Math.max(peakAltM, r.alt);
        }
        if (r.temp !== null && Number.isFinite(r.temp)) {
            minTempC = minTempC === null ? r.temp : Math.min(minTempC, r.temp);
        }
        if (r.lat !== null && r.lon !== null) {
            fixCount += 1;
            if (prev) distanceKm += haversineKm(prev.lat as number, prev.lon as number, r.lat, r.lon);
            prev = r;
        }
    }
    return { peakAltM, minTempC, distanceKm, fixCount, rowCount: rows.length, firstT, lastT };
}

/* ──────────────────────────────────────────────────────────────
 * Curated summaries — prefer the registry's published KPIs (the curated
 * narrative numbers) and only compute what the registry doesn't carry.
 * ────────────────────────────────────────────────────────────── */
function curatedSummaries(): PastFlightSummary[] {
    return CURATED_SOURCES.map((src) => {
        const report = FLIGHT_REPORTS.find((r) => r.slug === src.slug);
        const rows = src.samples.map((s) => ({
            t: src.launchMs + s.mins * 60_000,
            lat: s.lat,
            lon: s.lon,
            alt: s.alt_gps,
            temp: s.temp,
        }));
        const stats = computeTrackStats(rows);
        const durationHrs = report?.kpis.floatDuration ? parseFloat(report.kpis.floatDuration) : null;
        return {
            id: src.slug,
            source: 'curated' as const,
            callsign: report?.callsign ?? null,
            title: report?.title ?? null,
            subtitle: report?.subtitle ?? null,
            deviceId: report?.deviceId ?? src.slug,
            status: report?.status === 'in-flight' ? 'flying' : 'landed',
            launchedAtMs: src.launchMs,
            endedAtMs: stats.lastT,
            durationMs: durationHrs !== null ? durationHrs * 3_600_000 : (stats.lastT && stats.firstT ? stats.lastT - stats.firstT : null),
            peakAltM: report?.kpis.peakAltitudeM ?? stats.peakAltM,
            distanceKm: report?.kpis.groundCoverageKm ?? stats.distanceKm,
            minTempC: report?.kpis.minTempC ?? stats.minTempC,
            fixCount: report?.gpsFixes ?? stats.fixCount,
            rowCount: stats.rowCount,
            launchCoords: report?.launchCoords ?? null,
            comms: report?.comms ?? null,
        };
    });
}

/* ──────────────────────────────────────────────────────────────
 * usePastFlights — archive index data.
 * ────────────────────────────────────────────────────────────── */
export interface UsePastFlightsResult {
    flights: PastFlightSummary[];
    status: DataStatus;
    loading: boolean;
}

export function usePastFlights(): UsePastFlightsResult {
    const [flights, setFlights] = useState<PastFlightSummary[]>(() => curatedSummaries());
    const [status, setStatus] = useState<DataStatus>('connecting');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        async function load() {
            const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
            const curated = curatedSummaries();
            if (!url || url.includes('your_supabase') || url === '') {
                if (!cancelled) {
                    setFlights(curated);
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
                    .in('status', PAST_STATUSES)
                    .not('launched_at', 'is', null);
                if (devErr) throw devErr;

                const launched = (rawDevices ?? []).filter((d: any) => d.launched_at);
                const ids = launched.map((d: any) => d.device_id);

                let statRows: Array<StatRow & { device_id: string }> = [];
                if (ids.length) {
                    const launchTimes = launched
                        .map((d: any) => new Date(d.launched_at).getTime())
                        .filter((t: number) => Number.isFinite(t));
                    const earliest = launchTimes.length ? Math.min(...launchTimes) : Date.now() - MAX_MISSION_MS;
                    const since = new Date(Math.max(earliest, Date.now() - MAX_MISSION_MS)).toISOString();

                    const { data: tele, error: teleErr } = await supabase
                        .from('telemetry')
                        .select('device_id, time, lat, lon, altitude_m, temperature')
                        .in('device_id', ids)
                        .gte('time', since)
                        .order('time', { ascending: true })
                        .limit(FLIGHT_ROW_LIMIT);
                    if (teleErr) throw teleErr;
                    statRows = (tele ?? []).map((r: any) => ({
                        device_id: r.device_id,
                        t: new Date(r.time).getTime(),
                        lat: r.lat ?? null,
                        lon: r.lon ?? null,
                        alt: r.altitude_m ?? null,
                        temp: r.temperature ?? null,
                    }));
                }

                const byDevice = new Map<string, StatRow[]>();
                for (const r of statRows) {
                    const list = byDevice.get(r.device_id);
                    if (list) list.push(r);
                    else byDevice.set(r.device_id, [r]);
                }

                const dbFlights: PastFlightSummary[] = launched.map((d: any) => {
                    const launchedAtMs = d.launched_at ? new Date(d.launched_at).getTime() : null;
                    const stats = computeTrackStats(byDevice.get(d.device_id) ?? []);
                    const endedAtMs = stats.lastT;
                    const durationMs =
                        launchedAtMs !== null && endedAtMs !== null
                            ? endedAtMs - launchedAtMs
                            : stats.firstT !== null && endedAtMs !== null
                              ? endedAtMs - stats.firstT
                              : null;
                    const coords =
                        d.launch_lat != null && d.launch_lon != null
                            ? `${(+d.launch_lat).toFixed(3)}°, ${(+d.launch_lon).toFixed(3)}°`
                            : null;
                    return {
                        id: d.device_id,
                        source: 'db' as const,
                        callsign: d.launcher_name ?? null,
                        title: null,
                        subtitle: null,
                        deviceId: d.device_id,
                        status: d.status,
                        launchedAtMs,
                        endedAtMs,
                        durationMs,
                        peakAltM: stats.peakAltM,
                        distanceKm: stats.distanceKm,
                        minTempC: stats.minTempC,
                        fixCount: stats.fixCount,
                        rowCount: stats.rowCount,
                        launchCoords: coords,
                        comms: null,
                    };
                });

                if (cancelled) return;
                /* DB flights first (real missions), then curated fallback,
                 * each block sorted newest-launch-first. */
                const sortByLaunch = (a: PastFlightSummary, b: PastFlightSummary) =>
                    (b.launchedAtMs ?? 0) - (a.launchedAtMs ?? 0);
                setFlights([...dbFlights.sort(sortByLaunch), ...curated.sort(sortByLaunch)]);
                setStatus('connected');
                setLoading(false);
            } catch (e) {
                console.debug('usePastFlights error', e);
                if (!cancelled) {
                    setFlights(curated);
                    setStatus('error');
                    setLoading(false);
                }
            }
        }
        load();
        return () => {
            cancelled = true;
        };
    }, []);

    return { flights, status, loading };
}

/* ──────────────────────────────────────────────────────────────
 * useFlightReplay — full mission row set + metadata for one flight.
 * Curated flights resolve synchronously; DB flights fetch the entire
 * mission window (launch → last contact, capped), not the rolling 24h.
 * ────────────────────────────────────────────────────────────── */
function rawToTelemetry(raw: Record<string, any>): TelemetryRow {
    const presHpa = (raw.pressure ?? null) as number | null;
    return {
        t: new Date(raw.time).getTime(),
        lat: raw.lat ?? null,
        lon: raw.lon ?? null,
        alt: raw.altitude_m ?? null,
        temp: raw.temperature ?? null,
        pres: presHpa,
        presAlt: altitudeFromPressureHpa(presHpa),
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
        gateways: Array.isArray(raw.gateways) ? raw.gateways : null,
    };
}

export interface UseFlightReplayResult {
    rows: TelemetryRow[];
    meta: FlightReplayMeta | null;
    status: DataStatus;
    loading: boolean;
    notFound: boolean;
}

export function useFlightReplay(flightId: string | null): UseFlightReplayResult {
    const [rows, setRows] = useState<TelemetryRow[]>([]);
    const [meta, setMeta] = useState<FlightReplayMeta | null>(null);
    const [status, setStatus] = useState<DataStatus>('connecting');
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);

    useEffect(() => {
        let cancelled = false;
        if (!flightId) {
            setLoading(false);
            setNotFound(true);
            return;
        }

        /* Curated flights are local data — resolve immediately. */
        const curated = CURATED_SOURCES.find((c) => c.slug === flightId);
        if (curated) {
            const report = FLIGHT_REPORTS.find((r) => r.slug === curated.slug);
            const curatedRows = curatedToRows(curated.samples, curated.launchMs);
            setRows(curatedRows);
            setMeta({
                id: curated.slug,
                source: 'curated',
                callsign: report?.callsign ?? null,
                title: report?.title ?? null,
                subtitle: report?.subtitle ?? null,
                deviceId: report?.deviceId ?? curated.slug,
                status: report?.status === 'in-flight' ? 'flying' : 'landed',
                launchedAtMs: curated.launchMs,
                endedAtMs: curatedRows.length ? curatedRows[curatedRows.length - 1].t : null,
                comms: report?.comms ?? null,
                firmware: null,
            });
            setStatus('connected');
            setLoading(false);
            setNotFound(false);
            return;
        }

        async function load() {
            const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!url || url.includes('your_supabase') || url === '') {
                if (!cancelled) {
                    setStatus('disconnected');
                    setLoading(false);
                    setNotFound(true);
                }
                return;
            }
            try {
                const supabase = createClient();
                const { data: dev, error: devErr } = await supabase
                    .from('devices')
                    .select('device_id, launcher_name, status, launched_at')
                    .eq('device_id', flightId)
                    .maybeSingle();
                if (devErr) throw devErr;
                if (!dev) {
                    if (!cancelled) {
                        setStatus('connected');
                        setLoading(false);
                        setNotFound(true);
                    }
                    return;
                }

                const launchedAtMs = dev.launched_at ? new Date(dev.launched_at).getTime() : null;
                const sinceMs =
                    launchedAtMs !== null
                        ? Math.max(launchedAtMs, Date.now() - MAX_MISSION_MS)
                        : Date.now() - MAX_MISSION_MS;
                const since = new Date(sinceMs).toISOString();

                const { data, error } = await supabase
                    .from('telemetry')
                    .select(FULL_TELEMETRY_COLUMNS)
                    .eq('device_id', flightId)
                    .gte('time', since)
                    .order('time', { ascending: true })
                    .limit(FLIGHT_ROW_LIMIT);
                if (error) throw error;
                if (cancelled) return;

                const next = (data ?? []).map(rawToTelemetry);
                const latestWithFw = [...next].reverse().find((r) => r.firmware_version);
                setRows(next);
                setMeta({
                    id: dev.device_id,
                    source: 'db',
                    callsign: dev.launcher_name ?? null,
                    title: null,
                    subtitle: null,
                    deviceId: dev.device_id,
                    status: dev.status,
                    launchedAtMs,
                    endedAtMs: next.length ? next[next.length - 1].t : null,
                    comms: null,
                    firmware: latestWithFw?.firmware_version ?? null,
                });
                setStatus('connected');
                setLoading(false);
                setNotFound(false);
            } catch (e) {
                console.debug('useFlightReplay error', e);
                if (!cancelled) {
                    setStatus('error');
                    setLoading(false);
                }
            }
        }
        load();
        return () => {
            cancelled = true;
        };
    }, [flightId]);

    return { rows, meta, status, loading, notFound };
}
