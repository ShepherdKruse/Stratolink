import type { SupabaseClient } from '@supabase/supabase-js';
import { canonicalDeviceId, telemetryDeviceIds } from '@/lib/devices/aliases';

const PAGE_SIZE = 1000;

export type RawTelemetryRecord = Record<string, unknown>;

function rowQualityScore(row: RawTelemetryRecord): number {
    let score = 0;
    if (row.lat != null && row.lon != null) score += 4;
    if (row.altitude_m != null) score += 2;
    if (row.temperature != null) score += 1;
    if (row.pressure != null) score += 1;
    return score;
}

/** Merge rows from canonical + alias device_ids into one time-ordered series. */
export function mergeTelemetryByTime(rows: RawTelemetryRecord[]): RawTelemetryRecord[] {
    const byTime = new Map<string, RawTelemetryRecord>();
    for (const row of rows) {
        const key = String(row.time ?? '');
        if (!key) continue;
        const prev = byTime.get(key);
        if (!prev || rowQualityScore(row) > rowQualityScore(prev)) {
            byTime.set(key, row);
        }
    }
    return [...byTime.values()].sort(
        (a, b) => new Date(String(a.time)).getTime() - new Date(String(b.time)).getTime(),
    );
}

/**
 * Fetch full mission telemetry for a device, including alias ids (e.g. stratolink-3-eu → stratolink-3).
 * Paginates past Supabase's 1000-row page limit so long flights stay complete.
 */
export async function fetchTelemetryMerged(
    supabase: SupabaseClient,
    opts: {
        deviceId: string;
        since: string;
        columns: string;
        maxRows?: number;
    },
): Promise<RawTelemetryRecord[]> {
    const queryIds = telemetryDeviceIds(opts.deviceId);
    const cap = opts.maxRows ?? Number.POSITIVE_INFINITY;
    const collected: RawTelemetryRecord[] = [];
    let offset = 0;

    while (collected.length < cap) {
        const pageEnd = offset + PAGE_SIZE - 1;
        const { data, error } = await supabase
            .from('telemetry')
            .select(opts.columns)
            .in('device_id', queryIds)
            .gte('time', opts.since)
            .order('time', { ascending: true })
            .range(offset, pageEnd);

        if (error) throw error;
        const page = (data ?? []) as RawTelemetryRecord[];
        if (!page.length) break;

        collected.push(...page);
        if (page.length < PAGE_SIZE) break;
        offset += PAGE_SIZE;
    }

    const capped =
        Number.isFinite(cap) && collected.length > cap ? collected.slice(0, cap) : collected;
    return mergeTelemetryByTime(capped);
}

/** Latest uplink time across canonical + alias ids. */
export async function fetchLatestContactMs(
    supabase: SupabaseClient,
    deviceId: string,
    since: string,
): Promise<number | null> {
    const queryIds = telemetryDeviceIds(deviceId);
    const { data, error } = await supabase
        .from('telemetry')
        .select('time')
        .in('device_id', queryIds)
        .gte('time', since)
        .order('time', { ascending: false })
        .limit(1);

    if (error || !data?.[0]?.time) return null;
    return new Date(data[0].time as string).getTime();
}

export type LatestGpsFix = {
    lat: number;
    lon: number;
    alt: number | null;
    t: number;
};

/** Latest GPS fix across canonical + alias ids. */
export async function fetchLatestGpsFix(
    supabase: SupabaseClient,
    deviceId: string,
    since: string,
): Promise<LatestGpsFix | null> {
    const queryIds = telemetryDeviceIds(deviceId);
    const { data, error } = await supabase
        .from('telemetry')
        .select('lat, lon, altitude_m, time')
        .in('device_id', queryIds)
        .gte('time', since)
        .not('lat', 'is', null)
        .not('lon', 'is', null)
        .order('time', { ascending: false })
        .limit(1);

    if (error || !data?.[0]) return null;
    const row = data[0];
    return {
        lat: row.lat as number,
        lon: row.lon as number,
        alt: (row.altitude_m as number | null) ?? null,
        t: new Date(row.time as string).getTime(),
    };
}

export type FleetTelemetryLightRow = {
    device_id: string;
    time: string;
    lat: number | null;
    lon: number | null;
    rssi: number | null;
};

/** Paginated lightweight fleet telemetry for KPI aggregates (alias-aware). */
export async function fetchFleetTelemetryLight(
    supabase: SupabaseClient,
    telemetryIds: string[],
    fleetSince: string,
): Promise<FleetTelemetryLightRow[]> {
    if (!telemetryIds.length) return [];

    const collected: FleetTelemetryLightRow[] = [];
    let offset = 0;

    while (true) {
        const pageEnd = offset + PAGE_SIZE - 1;
        const { data, error } = await supabase
            .from('telemetry')
            .select('device_id, time, lat, lon, rssi')
            .in('device_id', telemetryIds)
            .gte('time', fleetSince)
            .order('time', { ascending: true })
            .range(offset, pageEnd);

        if (error) throw error;
        const page = (data ?? []) as FleetTelemetryLightRow[];
        if (!page.length) break;
        collected.push(...page);
        if (page.length < PAGE_SIZE) break;
        offset += PAGE_SIZE;
    }

    return collected;
}

export { canonicalDeviceId };
