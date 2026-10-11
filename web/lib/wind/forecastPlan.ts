/**
 * Forecast activity plan — the rules that decide which devices the worker
 * ingests this run, shared by scripts/plan_forecasts.ts and its tests.
 *
 * The worker's only gate used to be the manual `devices.status = 'flying'` flag,
 * so a bench unit or a long-lost balloon was re-ingested (GFS + 31 GEFS + 31
 * AIGEFS member cubes, ~15 GB) four times a day for months, producing exactly the
 * same forecast each time. A forecast is a fixed function of history once the
 * balloon's last fix is older than the dead-reckon cap: the tube then ends at
 * `last_fix + DEAD_RECKON_CAP_H` with no forward leg, and every field it samples
 * comes from a past NOAA cycle, which is immutable once published. Re-running it
 * can only reproduce the stored forecast.
 *
 * Pure: no I/O. The plan script gathers the inputs and writes the plan JSON that
 * gfs_ingest.py / gefs_ingest.py / aigefs_ingest.py / compute_forecasts.ts read.
 */

export const PLAN_VERSION = 1;

/** Mirrors HORIZON_H in scripts/gfs_ingest.py (and the compute's forecastHours). */
export const HORIZON_H = 24;
/** Mirrors DEAD_RECKON_CAP_H in scripts/gfs_ingest.py — the same env override. */
export const DEFAULT_DEAD_RECKON_CAP_H = 14 * 24;
/**
 * Hours past the capped dead-reckon before a stored forecast counts as final.
 * NOAA publishes a cycle's fields 3.5–7 h after the cycle time (AIGEFS the
 * slowest), so a forecast generated inside this margin may still have sampled
 * the then-latest cycle's forecast hours for the tube's last few slices rather
 * than the analysis a later run would use. One horizon (24 h) covers every
 * source's publication lag with room to spare; it costs at most ~4 extra runs
 * per dark balloon.
 */
export const FREEZE_MARGIN_H = HORIZON_H;

export type PlanConfig = {
    horizonH: number;
    deadReckonCapH: number;
    freezeMarginH: number;
};

export function planConfigFromEnv(env: NodeJS.ProcessEnv = process.env): PlanConfig {
    const cap = Number(env.FC_DEAD_RECKON_CAP_H ?? DEFAULT_DEAD_RECKON_CAP_H);
    return {
        horizonH: HORIZON_H,
        deadReckonCapH: Number.isFinite(cap) && cap > 0 ? cap : DEFAULT_DEAD_RECKON_CAP_H,
        freezeMarginH: FREEZE_MARGIN_H,
    };
}

export type StoredForecastSummary = {
    generated_at: string;
    /** Time of the last GPS fix (or launch pseudo-fix) the stored forecast was built from. */
    last_fix_utc: string | null;
};

export type PlanDeviceInput = {
    deviceId: string;
    launchedAt: string | null;
    /** Last GPS fix in the mission window; the launch record stands in when there are none. */
    lastFixUtc: string | null;
    /** GPS fixes in the mission window (0 ⇒ launch-only mode or nothing to forecast). */
    nFixes: number;
    hasLaunchRecord: boolean;
    stored: StoredForecastSummary | null;
    /** Operator override: build even when the stored forecast is already final. */
    force?: boolean;
};

export type PlanAction = 'build' | 'skip';

export type PlanDevice = {
    device_id: string;
    action: PlanAction;
    reason: string;
    launched_at: string | null;
    /** The fix (or launch record) the forecast would start from. */
    origin_utc: string | null;
    origin_age_h: number | null;
    n_fixes: number;
    stored_generated_at: string | null;
};

export type ForecastPlan = {
    version: number;
    generated_at: string;
    config: { horizon_h: number; dead_reckon_cap_h: number; freeze_margin_h: number };
    requested_device: string | null;
    force: boolean;
    devices: PlanDevice[];
};

const HOUR_MS = 3_600_000;

function parseMs(iso: string | null | undefined): number | null {
    if (!iso) return null;
    const ms = Date.parse(iso);
    return Number.isFinite(ms) ? ms : null;
}

const fmtH = (h: number) => (h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`);

/**
 * Decide one device. The device is assumed to be flying + connected (the plan
 * script lists those); this only asks whether a run can change its forecast.
 */
export function decideDevice(d: PlanDeviceInput, cfg: PlanConfig, nowMs = Date.now()): PlanDevice {
    const base = {
        device_id: d.deviceId,
        launched_at: d.launchedAt,
        n_fixes: d.nFixes,
        stored_generated_at: d.stored?.generated_at ?? null,
    };

    /* Nothing to start from: no fix in the mission window and no launch record
     * (or the launch is still in the future). The compute would return null for
     * it too, so the ingest would be pure waste. */
    const originUtc = d.nFixes > 0 ? d.lastFixUtc : d.hasLaunchRecord ? d.launchedAt : null;
    const originMs = parseMs(originUtc);
    if (originMs == null) {
        return {
            ...base, action: 'skip', origin_utc: null, origin_age_h: null,
            reason: d.nFixes > 0
                ? 'last fix has no parseable time'
                : 'no GPS fixes in the mission window and no launch record',
        };
    }

    const ageH = (nowMs - originMs) / HOUR_MS;
    const origin = { origin_utc: originUtc, origin_age_h: Math.round(ageH * 10) / 10 };
    const what = d.nFixes > 0 ? 'last fix' : 'launch record';
    const finalAfterH = cfg.deadReckonCapH + cfg.freezeMarginH;

    if (ageH <= finalAfterH) {
        return {
            ...base, ...origin, action: 'build',
            reason: ageH <= cfg.deadReckonCapH
                ? `${what} ${fmtH(ageH)} ago — forecast still evolves`
                : `${what} ${fmtH(ageH)} ago — capped dead-reckon not final until +${fmtH(finalAfterH)}`,
        };
    }

    /* Past the cap + margin: the tube is entirely past-cycle. Skip only when a
     * stored forecast already captured exactly that — same origin fix, generated
     * after every field it needs became immutable. */
    const frozenAtMs = originMs + finalAfterH * HOUR_MS;
    const storedMs = parseMs(d.stored?.generated_at);
    const storedFixMs = parseMs(d.stored?.last_fix_utc);
    const sameOrigin = storedFixMs != null && Math.abs(storedFixMs - originMs) < 1000;

    if (d.force) {
        return { ...base, ...origin, action: 'build', reason: `forced rebuild (${what} ${fmtH(ageH)} ago)` };
    }
    if (!d.stored || storedMs == null) {
        return { ...base, ...origin, action: 'build', reason: `${what} ${fmtH(ageH)} ago and no stored forecast yet` };
    }
    if (!sameOrigin) {
        return {
            ...base, ...origin, action: 'build',
            reason: `stored forecast starts from ${d.stored.last_fix_utc ?? 'an unknown fix'}, not ${originUtc}`,
        };
    }
    if (storedMs < frozenAtMs) {
        return {
            ...base, ...origin, action: 'build',
            reason: `stored forecast (${d.stored.generated_at}) predates the final capped dead-reckon`,
        };
    }
    return {
        ...base, ...origin, action: 'skip',
        reason: `frozen: ${what} ${fmtH(ageH)} ago (> cap ${fmtH(cfg.deadReckonCapH)} + ${fmtH(cfg.freezeMarginH)}); `
            + `stored forecast from ${d.stored.generated_at} is already the final dead-reckon`,
    };
}

/** The last fix a stored forecast was built from: its observed fixes (the launch
 *  pseudo-fix in launch-only mode) or, for a stale forecast, `stale_gps`. */
export function storedForecastSummary(stored: {
    generated_at?: string;
    observed?: { gps_fixes?: Array<{ time_utc?: string }> };
    stale_gps?: { last_fix_time_utc?: string } | null;
} | null): StoredForecastSummary | null {
    if (!stored?.generated_at) return null;
    const fixes = stored.observed?.gps_fixes ?? [];
    const last = fixes.length ? fixes[fixes.length - 1]?.time_utc : undefined;
    return { generated_at: stored.generated_at, last_fix_utc: last ?? stored.stale_gps?.last_fix_time_utc ?? null };
}

/** Plans older than this are ignored by every consumer (a stale local file must
 *  never silently shrink the fleet). */
export const PLAN_MAX_AGE_H = 12;

export function planIsFresh(plan: { generated_at?: string } | null, nowMs = Date.now()): boolean {
    const ms = parseMs(plan?.generated_at);
    return ms != null && nowMs - ms <= PLAN_MAX_AGE_H * HOUR_MS && ms <= nowMs + HOUR_MS;
}
