/**
 * Plan step — decides which devices the forecast worker ingests THIS run and
 * writes the plan JSON that gfs_ingest.py, gefs_ingest.py, aigefs_ingest.py and
 * compute_forecasts.ts consume. Runs first in .github/workflows/gfs-ingest.yml.
 *
 * Rules live in lib/wind/forecastPlan.ts (pure, tested). In short: a flying,
 * connected device is built unless its forecast cannot change — last fix (or
 * launch record) older than DEAD_RECKON_CAP_H + a publication-lag margin AND a
 * stored forecast from the same fix generated after that point — or it has
 * nothing to start from (no fixes, no launch record).
 *
 * Usage:  npx tsx scripts/plan_forecasts.ts [deviceId] [--force] [--dry]
 *   deviceId → plan just that device (any status, must be connected)
 *   --force  → (or FORCE=true) build even when the stored forecast is final
 *   --dry    → print the plan, write nothing
 * Env: NEXT_PUBLIC_SUPABASE_URL (or SUPABASE_URL), SUPABASE_SERVICE_ROLE_KEY,
 *      BLOB_READ_WRITE_TOKEN (stored forecasts; .forecast-cache/ without it),
 *      FORECAST_PLAN (output, default .windcube/plan.json),
 *      FORECAST_MANIFEST (reset here, default .windcube/manifest.json),
 *      FC_DEAD_RECKON_CAP_H (must match the ingest's).
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { isHiddenAliasDevice } from '@/lib/devices/aliases';
import { createServiceRoleClient } from '@/lib/supabase';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { readStoredForecast } from '@/lib/wind/forecastStorage';
import { emptyManifest, writeManifest } from '@/lib/wind/forecastManifest';
import {
    decideDevice, planConfigFromEnv, storedForecastSummary,
    PLAN_VERSION, type ForecastPlan, type PlanDevice,
} from '@/lib/wind/forecastPlan';

export const PLAN_PATH = process.env.FORECAST_PLAN ?? join(process.cwd(), '.windcube', 'plan.json');
export const MANIFEST_PATH = process.env.FORECAST_MANIFEST ?? join(process.cwd(), '.windcube', 'manifest.json');

type DeviceRow = {
    device_id: string;
    status: string | null;
    launched_at: string | null;
    launch_lat: number | null;
    launch_lon: number | null;
};

async function listDevices(only: string | null): Promise<DeviceRow[]> {
    const supabase = createServiceRoleClient();
    let q = supabase
        .from('devices')
        .select('device_id, status, launched_at, launch_lat, launch_lon')
        .eq('connection_status', 'connected')
        .order('device_id', { ascending: true });
    /* An explicitly requested device is planned whatever its status flag (the
     * operator asked for it); the fleet run takes the flying ones. */
    q = only ? q.eq('device_id', only) : q.eq('status', 'flying');
    const { data, error } = await q;
    if (error) throw new Error(`devices query failed: ${error.message}`);
    return ((data ?? []) as DeviceRow[]).filter((d) => !isHiddenAliasDevice(d.device_id));
}

async function planOne(d: DeviceRow, force: boolean, nowMs: number): Promise<PlanDevice> {
    const launchMs = d.launched_at ? Date.parse(d.launched_at) : NaN;
    const hasLaunchRecord =
        d.launch_lat != null && d.launch_lon != null && Number.isFinite(launchMs) && launchMs <= nowMs;

    /* Same loader as the compute, so the fixes the plan reasons about are exactly
     * the fixes the forecast will be built from (mission window, alias merge). */
    const input = await buildForecastInputForDevice(d.device_id);
    let nFixes = 0;
    let lastFixUtc: string | null = null;
    if (input) {
        const last = input.gpsFixes[input.gpsFixes.length - 1];
        const launchOnly =
            hasLaunchRecord && input.gpsFixes.length === 1 && last.lat === d.launch_lat &&
            last.lon === d.launch_lon && Date.parse(last.time_utc) === launchMs;
        nFixes = launchOnly ? 0 : input.gpsFixes.length;
        lastFixUtc = launchOnly ? null : last?.time_utc ?? null;
    }

    const stored = storedForecastSummary(await readStoredForecast(d.device_id));
    return decideDevice(
        { deviceId: d.device_id, launchedAt: d.launched_at, lastFixUtc, nFixes, hasLaunchRecord, stored, force },
        planConfigFromEnv(),
        nowMs,
    );
}

async function main(): Promise<void> {
    const args = process.argv.slice(2).filter(Boolean);
    const dry = args.includes('--dry');
    const force = args.includes('--force') || /^(1|true)$/i.test(process.env.FORCE ?? '');
    const ids = args.filter((a) => a !== '--dry' && a !== '--force');
    if (ids.length > 1 || ids.some((id) => id.startsWith('-') || !/^[a-zA-Z0-9_-]{1,80}$/.test(id))) {
        throw new Error('Invalid forecast device argument');
    }
    const only = ids[0] ?? null;
    const nowMs = Date.now();
    const cfg = planConfigFromEnv();

    const rows = await listDevices(only);
    if (only && !rows.length) throw new Error(`Device ${only} is not a connected registry entry`);

    const devices: PlanDevice[] = [];
    for (const d of rows) {
        const p = await planOne(d, force, nowMs);
        devices.push(p);
        console.log(`  ${p.device_id}: ${p.action.toUpperCase()} — ${p.reason}`);
    }

    const plan: ForecastPlan = {
        version: PLAN_VERSION,
        generated_at: new Date(nowMs).toISOString(),
        config: { horizon_h: cfg.horizonH, dead_reckon_cap_h: cfg.deadReckonCapH, freeze_margin_h: cfg.freezeMarginH },
        requested_device: only,
        force,
        devices,
    };
    const build = devices.filter((d) => d.action === 'build').length;
    console.log(
        `plan: ${devices.length} device(s) considered, ${build} to build, ${devices.length - build} skipped` +
        (devices.length ? '' : only ? '' : ' (no active devices)') + (dry ? ' — dry run, nothing written' : ''),
    );
    if (dry) return;
    mkdirSync(dirname(PLAN_PATH), { recursive: true });
    writeFileSync(PLAN_PATH, JSON.stringify(plan, null, 1));
    /* A fresh manifest per run: the ingest steps append to it, the summary reads it. */
    writeManifest(MANIFEST_PATH, emptyManifest(plan.generated_at));
    console.log(`wrote ${PLAN_PATH}`);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
