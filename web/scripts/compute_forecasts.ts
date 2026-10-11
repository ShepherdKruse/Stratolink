/**
 * Worker-side forecast compute (runs in GitHub Actions, after gfs_ingest.py).
 *
 * Instead of a Vercel serverless function pulling each cube out of Blob and
 * JSON-parsing it on every cron tick — which caps out on function memory/time and
 * re-reads the cube every ~30 min — this computes the forecast ON THE RUNNER,
 * reading the cubes the ingest just wrote to local disk (`WIND_CUBE_DIR`), and
 * uploads ONLY the small forecast JSON to Blob (via `storeForecast`, the same path
 * `/api/forecast` reads). The big wind data never touches a serverless function.
 *
 * This is also where a 31-member GEFS ensemble belongs: the heavy per-member
 * integration runs here (no serverless caps), and the browser still just fetches a
 * few-hundred-KB forecast JSON.
 *
 * Which devices: the plan written by scripts/plan_forecasts.ts (FORECAST_PLAN),
 * falling back to every device with a forecast (`-fc`) cube in WIND_CUBE_DIR when
 * there is no fresh plan (local runs). The ingest manifest (FORECAST_MANIFEST)
 * supplies the configured member counts, which are printed and stamped into
 * `metadata.members` / `metadata.members_expected` so a truncated ensemble is
 * visible in the stored forecast, not just in a killed step's log.
 *
 * Usage:  npx tsx scripts/compute_forecasts.ts [deviceId] [--dry]
 *   no deviceId → every planned device (or every device with a cube)
 *   --dry       → compute + print, do NOT store
 * Env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BLOB_READ_WRITE_TOKEN,
 *      WIND_CUBE_DIR (defaults to ./.windcube/cubes), FORECAST_PLAN, FORECAST_MANIFEST.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import { storeForecast } from '@/lib/wind/forecastStorage';
import { listMemberCubes } from '@/lib/wind/windCube';
import { planIsFresh, type ForecastPlan, type PlanDevice } from '@/lib/wind/forecastPlan';
import {
    emptyManifest, ensembleMembers, formatMembers, readManifest, writeManifest,
    type ForecastManifest, type ManifestSource, type ManifestSourceDevice,
} from '@/lib/wind/forecastManifest';

const CUBE_DIR = process.env.WIND_CUBE_DIR ?? join(process.cwd(), '.windcube', 'cubes');
process.env.WIND_CUBE_DIR = CUBE_DIR; // ensure fetchWindCube reads local cubes by device
const PLAN_PATH = process.env.FORECAST_PLAN ?? join(process.cwd(), '.windcube', 'plan.json');
const MANIFEST_PATH = process.env.FORECAST_MANIFEST ?? join(process.cwd(), '.windcube', 'manifest.json');

/** Devices to compute = those the ingest just built a (forecast) cube for. */
function devicesFromCubes(dir: string): string[] {
    let files: string[] = [];
    try { files = readdirSync(dir); } catch { return []; }
    /* Key on the FORECAST cube `{device}-fc.slwc` (packed binary; `.json` kept as a
     * legacy fallback): a device with a single fix gets no reconstruction cube at
     * all, but it still has a forecast tube and a forecast to compute. The
     * ensemble member cubes (`-mNN`/`-aNN`) are not standalone devices. */
    const ids = files
        .map((f) => f.match(/^(.+)-fc\.(slwc|json)(\.gz)?$/)?.[1])
        .filter((id): id is string => Boolean(id))
        .map((id) => decodeURIComponent(id));
    /* Dedupe — a device may have both `{id}-fc.slwc` and a legacy `{id}-fc.json`
     * during the format transition; compute it once. */
    return [...new Set(ids)];
}

/** The plan step's decisions for this run; null when there is no (fresh) plan —
 *  then the cubes on disk decide. */
function readPlan(path: string): PlanDevice[] | null {
    let plan: ForecastPlan;
    try { plan = JSON.parse(readFileSync(path, 'utf8')) as ForecastPlan; } catch { return null; }
    if (!planIsFresh(plan)) {
        console.log(`ignoring stale plan ${path} (generated ${plan.generated_at ?? 'unknown'})`);
        return null;
    }
    return plan.devices ?? [];
}

async function main(): Promise<void> {
    const args = process.argv.slice(2).filter(Boolean);
    const dry = args.includes('--dry');
    const ids = args.filter(a => a !== '--dry');
    if (ids.length > 1 || ids.some(id => id.startsWith('-') || !/^[a-zA-Z0-9_-]{1,80}$/.test(id))) throw new Error('Invalid forecast device argument');
    const only = ids[0];
    const planned = readPlan(PLAN_PATH);
    const available = planned ? planned.filter((d) => d.action === 'build').map((d) => d.device_id) : devicesFromCubes(CUBE_DIR);
    if (only && !available.includes(only)) {
        /* A requested device the plan decided to skip is not an error — the ingest
         * steps were no-ops for it too; say why and finish clean. */
        const skipped = planned?.find((d) => d.device_id === only && d.action !== 'build');
        if (skipped) {
            console.log(`  ${only}: skipped by plan — ${skipped.reason}`);
            return;
        }
        throw new Error(planned ? `No planned build for the requested device (see ${PLAN_PATH})` : 'No ingested cube for the requested device');
    }
    const devices = only ? [only] : available;

    if (!devices.length) {
        console.log(planned ? `plan ${PLAN_PATH} has no devices to build — nothing to compute` : `no device cubes in ${CUBE_DIR} — nothing to compute`);
        return;
    }
    console.log(`computing ${devices.length} forecast(s) from ${CUBE_DIR}${planned ? ' (per plan)' : ''}${dry ? ' (dry run)' : ''}`);

    /* Ingest manifest: read the member expectations, append this step's own record. */
    const manifest: ForecastManifest = readManifest(MANIFEST_PATH) ?? emptyManifest();
    const computed: Record<string, ManifestSourceDevice> = {};
    const compute: ManifestSource = { started_at: new Date().toISOString(), devices: computed };
    manifest.sources.compute = compute;
    const t0All = Date.now();
    const record = (id: string, fields: ManifestSourceDevice) => {
        computed[id] = fields;
        if (!dry) writeManifest(MANIFEST_PATH, manifest);
    };

    let ok = 0;
    for (const id of devices) {
        const t0 = Date.now();
        try {
            const input = await buildForecastInputForDevice(id);
            if (!input) {
                console.log(`  ${id}: insufficient telemetry, skipped`);
                record(id, { error: 'insufficient telemetry', seconds: (Date.now() - t0) / 1000 });
                continue;
            }
            const forecast = await computeMonteCarloForecast(input);
            /* Member accounting: what is on disk (what the ensemble just loaded) vs
             * what the ingest was configured to build. */
            const members = ensembleMembers(await listMemberCubes(id), manifest, id);
            forecast.metadata.members = members.members;
            if (Object.keys(members.expected).length) forecast.metadata.members_expected = members.expected;
            const url = dry ? null : await storeForecast(id, forecast);
            const e = forecast.endpoint;
            console.log(
                `  ${id}: ${Date.now() - t0}ms | source ${forecast.metadata?.wind_source}` +
                ` | ensemble ${forecast.metadata.n_ensemble} (${formatMembers(members)})${members.complete ? '' : ' INCOMPLETE'}` +
                ` | endpoint ${e.lat.toFixed(2)},${e.lon.toFixed(2)}` +
                (dry ? ' | (dry, not stored)' : ` | stored ${url ?? '(local)'}`),
            );
            record(id, {
                n_ensemble: forecast.metadata.n_ensemble, members: members.members, members_expected: members.expected,
                complete: members.complete, stored: !dry, seconds: (Date.now() - t0) / 1000,
            });
            ok++;
        } catch (err) {
            console.error(`  ${id}: FAILED ${err instanceof Error ? err.message : err}`);
            record(id, { error: err instanceof Error ? err.message : String(err), seconds: (Date.now() - t0) / 1000 });
        }
    }
    compute.finished_at = new Date().toISOString();
    compute.seconds = (Date.now() - t0All) / 1000;
    if (!dry) writeManifest(MANIFEST_PATH, manifest);
    console.log(`done: ${ok}/${devices.length} forecast(s) computed${dry ? '' : ' + stored'}`);
    if (ok !== devices.length) throw new Error(`${devices.length - ok} forecast(s) were not produced`);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
