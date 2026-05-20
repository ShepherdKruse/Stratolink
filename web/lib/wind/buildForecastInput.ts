import { createServiceRoleClient } from '@/lib/supabase';
import { telemetrySinceIso, type MissionWindowDevice } from '@/lib/telemetry/missionWindow';
import { splitTrackSegments } from '@/lib/wind/trackSegments';
import type { MonteCarloForecastInput } from '@/lib/wind/forecastTypes';

const TELEMETRY_COLUMNS = 'time, lat, lon, altitude_m, pressure';

export type DeviceRow = {
    device_id: string;
    launcher_name: string | null;
    status: string | null;
    launch_lat: number | null;
    launch_lon: number | null;
    launched_at: string | null;
};

/** Build Monte Carlo input from Supabase telemetry (server-only). */
export async function buildForecastInputForDevice(
    deviceId: string,
    forecastHours = 24,
): Promise<MonteCarloForecastInput | null> {
    const supabase = createServiceRoleClient();

    const { data: device, error: devErr } = await supabase
        .from('devices')
        .select('device_id, launcher_name, status, launch_lat, launch_lon, launched_at')
        .eq('device_id', deviceId)
        .maybeSingle();

    if (devErr || !device) return null;

    const mission: MissionWindowDevice = {
        status: device.status,
        launchedAt: device.launched_at ? new Date(device.launched_at).getTime() : null,
    };
    const since = telemetrySinceIso(mission);

    const { data: rows, error: telErr } = await supabase
        .from('telemetry')
        .select(TELEMETRY_COLUMNS)
        .eq('device_id', deviceId)
        .gte('time', since)
        .order('time', { ascending: true });

    if (telErr || !rows?.length) return null;

    const observedTrack = rows
        .filter((r) => r.lat != null && r.lon != null)
        .map((r) => ({
            lat: r.lat as number,
            lon: r.lon as number,
            t: r.time as string,
            alt_m: (r.altitude_m as number | null) ?? undefined,
        }));

    if (observedTrack.length < 1) return null;

    const baroSamples = rows
        .filter((r) => {
            const alt = r.altitude_m as number | null;
            return alt != null && Number.isFinite(alt) && alt > 0;
        })
        .map((r) => ({
            time_utc: r.time as string,
            alt_m: r.altitude_m as number,
        }));

    const first = observedTrack[0];
    const last = observedTrack[observedTrack.length - 1];
    const launch =
        device.launch_lat != null && device.launch_lon != null && device.launched_at
            ? {
                  lat: device.launch_lat,
                  lon: device.launch_lon,
                  time_utc: device.launched_at,
              }
            : { lat: first.lat, lon: first.lon, time_utc: first.t };

    const segments = splitTrackSegments(
        observedTrack.map((p) => ({ lat: p.lat, lon: p.lon, t: p.t })),
    );
    const driftSegment = segments.freezeDrift.length >= 2 ? segments.freezeDrift : undefined;

    const latestPres = [...rows].reverse().find((r) => r.pressure != null)?.pressure;
    const pressureHpa = typeof latestPres === 'number' && latestPres > 0 ? latestPres : 285;

    return {
        deviceId,
        mission: device.launcher_name ?? deviceId,
        launch,
        gpsFixes: observedTrack.map((p) => ({
            lat: p.lat,
            lon: p.lon,
            time_utc: p.t,
            alt_m: p.alt_m,
        })),
        observedTrackLonLat: observedTrack.map((p) => [p.lon, p.lat] as [number, number]),
        driftSegmentLonLat: driftSegment,
        baroSamples: baroSamples.length > 0 ? baroSamples : undefined,
        pressureHpa,
        forecastHours,
    };
}

/** Devices worth refreshing: flying, or any with a GPS fix in the last 24h. */
export async function listForecastDeviceIds(): Promise<string[]> {
    const supabase = createServiceRoleClient();
    const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

    const { data: devices, error } = await supabase
        .from('devices')
        .select('device_id, status')
        .order('device_id', { ascending: true });

    if (error || !devices?.length) return [];

    const ids = devices.map((d) => d.device_id);
    const { data: fixes } = await supabase
        .from('telemetry')
        .select('device_id')
        .in('device_id', ids)
        .gte('time', since)
        .not('lat', 'is', null)
        .not('lon', 'is', null);

    const withFix = new Set((fixes ?? []).map((r) => r.device_id));
    return devices
        .filter((d) => d.status === 'flying' || withFix.has(d.device_id))
        .map((d) => d.device_id);
}
