import { createServiceRoleClient } from '@/lib/supabase';
import { fetchTelemetryMerged } from '@/lib/telemetry/fetchMergedTelemetry';
import { telemetrySinceIso, type MissionWindowDevice } from '@/lib/telemetry/missionWindow';
import { splitTrackSegments } from '@/lib/wind/trackSegments';
import type { MonteCarloForecastInput } from '@/lib/wind/forecastTypes';

const TELEMETRY_COLUMNS = 'time, lat, lon, altitude_m, pressure';

/** A telemetry pressure that is a plausible float reading (80–400 hPa, the band
 *  scripts/gfs_ingest.py `float_pressure` uses), else undefined. */
function floatPressure(p: unknown): number | undefined {
    return typeof p === 'number' && p >= 80 && p <= 400 ? p : undefined;
}

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
        .eq('connection_status', 'connected')
        .maybeSingle();

    if (devErr || !device) return null;

    const mission: MissionWindowDevice = {
        status: device.status,
        launchedAt: device.launched_at ? new Date(device.launched_at).getTime() : null,
    };
    /* Full flight since launch (capped at MAX_HISTORY_MS), matching the dashboard's
     * selected-device window — so the reconstructed route line covers the WHOLE
     * mission, not just the rolling forecast window. Without this the hindcast
     * rolls older segments off the map as the 14-day window advances.
     * NB: this makes the reconstruction span every gap in the flight; it's cached
     * by a hash of the fixes, but see TODO(forecast-uncertainty) — the
     * reconstruction's per-gap wind fetches should eventually move onto the shared
     * WindCube to bound their cost for long, gappy missions. */
    /* FORECAST_HISTORY_DAYS lifts the 90-day full-history cap for a local replay
     * of an older flight (the cap would otherwise drop every fix of a months-old
     * reference mission and fall back to the launch record). Pair it with the
     * ingest's HISTORY_DAYS so the cube spans the same fixes. */
    const historyDays = Number(process.env.FORECAST_HISTORY_DAYS);
    const since = telemetrySinceIso(mission, Date.now(), {
        fullHistory: true,
        ...(Number.isFinite(historyDays) && historyDays > 0 ? { maxHistoryMs: historyDays * 86_400_000 } : {}),
    });

    let rows: Awaited<ReturnType<typeof fetchTelemetryMerged>>;
    try {
        rows = await fetchTelemetryMerged(supabase, {
            deviceId,
            since,
            columns: TELEMETRY_COLUMNS,
        });
    } catch {
        return null;
    }

    /* A device that has been released but not heard since (radio blackout, or
     * transmitting without GPS lock) has a mission window with zero fixes in
     * it — but the launch record (site + stamped time) is still real
     * information, and the honest forecast is a simulation seeded from
     * exactly that and nothing else. Pre-launch bench fixes never enter here:
     * the mission window already starts at launched_at. */
    const launchMs = device.launched_at ? new Date(device.launched_at).getTime() : null;
    const hasLaunchRecord =
        device.launch_lat != null &&
        device.launch_lon != null &&
        launchMs != null &&
        launchMs <= Date.now();

    if (!rows.length && !hasLaunchRecord) return null;

    /* Drop corrupt coordinates (the telemetry has occasional garbage fixes, e.g.
     * lat -222) — mirrors mission_fixes in scripts/gfs_ingest.py, so the cube and
     * the compute see the same fix set; a garbage fix would otherwise anchor a
     * bridge to a point no cube covers. */
    const validCoord = (lat: unknown, lon: unknown): boolean =>
        typeof lat === 'number' && typeof lon === 'number' &&
        Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    let observedTrack = rows
        .filter((r) => validCoord(r.lat, r.lon))
        .map((r) => ({
            lat: r.lat as number,
            lon: r.lon as number,
            t: r.time as string,
            alt_m: (r.altitude_m as number | null) ?? undefined,
            pressure_hpa: floatPressure(r.pressure),
        }));

    if (observedTrack.length < 1) {
        if (!hasLaunchRecord) return null;
        /* Launch-only mode: the launch point is the sole "fix". With no rows,
         * pressureHpa falls back to its float-level default below, so the
         * drift runs at altitude winds, not the surface layer. (The first
         * ~90 min of real ascent aren't modelled — acceptable for a
         * blackout estimate, and superseded by the first real packet.) */
        observedTrack = [{
            lat: device.launch_lat as number,
            lon: device.launch_lon as number,
            t: new Date(launchMs as number).toISOString(),
            alt_m: undefined,
            pressure_hpa: undefined,
        }];
    }

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
        observedTrack.map((p) => ({ lat: p.lat, lon: p.lon, t: new Date(p.t).getTime() })),
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
            ...(p.pressure_hpa != null ? { pressure_hpa: p.pressure_hpa } : {}),
        })),
        observedTrackLonLat: observedTrack.map((p) => [p.lon, p.lat] as [number, number]),
        driftSegmentLonLat: driftSegment,
        baroSamples: baroSamples.length > 0 ? baroSamples : undefined,
        pressureHpa,
        forecastHours,
    };
}
