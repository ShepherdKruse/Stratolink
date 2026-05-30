/**
 * Telemetry time-window helpers.
 *
 * Flying devices load everything since `launched_at` (capped) so an
 * overnight gap does not roll prior mission data off the dashboard.
 * Idle / landed / retired devices keep the rolling 24h window.
 */

const ROLLING_MS = 24 * 60 * 60 * 1000;
/** Safety cap so a forgotten `flying` row never pulls unbounded history. */
const MAX_MISSION_MS = 14 * 24 * 60 * 60 * 1000;
/** Cap for full-history (replay) queries — long enough for any past flight,
 *  bounded so a misconfigured launch date can't pull years of rows. */
const MAX_HISTORY_MS = 90 * 24 * 60 * 60 * 1000;

export interface MissionWindowDevice {
    status?: string | null;
    launchedAt?: number | null;
}

/** Options for the single-device window. */
export interface TelemetrySinceOpts {
    /** When true, load the device's entire flight since launch regardless of
     *  status (capped at MAX_HISTORY_MS). Used when the operator selects a
     *  landed/retired balloon to replay its full mission. Falls back to the
     *  rolling window when the device has no launch time. */
    fullHistory?: boolean;
}

function parseLaunchMs(launchedAt: number | string | null | undefined): number | null {
    if (launchedAt == null) return null;
    const ms = typeof launchedAt === 'number' ? launchedAt : new Date(launchedAt).getTime();
    return Number.isFinite(ms) ? ms : null;
}

/** Earliest timestamp to include for a single device's telemetry query. */
export function telemetrySinceMs(
    device: MissionWindowDevice,
    now = Date.now(),
    opts: TelemetrySinceOpts = {},
): number {
    const launchMs = parseLaunchMs(device.launchedAt ?? null);

    /* Replay mode: anchor to launch (capped) for any status. */
    if (opts.fullHistory && launchMs != null) {
        const capped = Math.max(launchMs, now - MAX_HISTORY_MS);
        return Math.min(capped, now);
    }

    const rolling = now - ROLLING_MS;
    if (device.status !== 'flying') return rolling;
    if (launchMs == null) return rolling;

    const capped = Math.max(launchMs, now - MAX_MISSION_MS);
    return Math.min(capped, now);
}

export function telemetrySinceIso(
    device: MissionWindowDevice,
    now = Date.now(),
    opts: TelemetrySinceOpts = {},
): string {
    return new Date(telemetrySinceMs(device, now, opts)).toISOString();
}

/** Fleet-wide lower bound: must include every flying device's full mission. */
export function fleetTelemetrySinceMs(devices: MissionWindowDevice[], now = Date.now()): number {
    const rolling = now - ROLLING_MS;
    let since = rolling;
    for (const d of devices) {
        since = Math.min(since, telemetrySinceMs(d, now));
    }
    return since;
}

export function fleetTelemetrySinceIso(devices: MissionWindowDevice[], now = Date.now()): string {
    return new Date(fleetTelemetrySinceMs(devices, now)).toISOString();
}
