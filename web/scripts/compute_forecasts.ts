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
 * Usage:  npx tsx scripts/compute_forecasts.ts [deviceId] [--dry]
 *   no deviceId → every device with a cube in WIND_CUBE_DIR
 *   --dry       → compute + print, do NOT store
 * Env: NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BLOB_READ_WRITE_TOKEN,
 *      WIND_CUBE_DIR (defaults to ./.windcube/cubes).
 */
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import { storeForecast } from '@/lib/wind/forecastStorage';

const CUBE_DIR = process.env.WIND_CUBE_DIR ?? join(process.cwd(), '.windcube', 'cubes');
process.env.WIND_CUBE_DIR = CUBE_DIR; // ensure fetchWindCube reads local cubes by device

/** Devices to compute = those the ingest just built a (reconstruction) cube for. */
function devicesFromCubes(dir: string): string[] {
    let files: string[] = [];
    try { files = readdirSync(dir); } catch { return []; }
    /* The device reconstruction cube is `{device}.slwc` (packed binary; `.json`
     * kept as a legacy fallback). EXCLUDE the forecast cube (`-fc`) and the
     * ensemble member cubes (`-mNN`/`-aNN`/`-eNN`) — those aren't standalone
     * devices. Cubes migrated JSON→.slwc, so matching only `.json` here silently
     * found zero devices and the scheduled (no-arg) compute became a no-op. */
    const isMember = /-[mae]\d+\.(slwc|json)$/;
    const ids = files
        .filter((f) =>
            (f.endsWith('.slwc') || f.endsWith('.json')) &&
            !f.endsWith('-fc.slwc') && !f.endsWith('-fc.json') &&
            !isMember.test(f))
        .map((f) => f.replace(/\.(slwc|json)$/, ''));
    /* Dedupe — a device may have both `{id}.slwc` and a legacy `{id}.json`
     * during the format transition; compute it once. */
    return [...new Set(ids)];
}

async function main(): Promise<void> {
    const args = process.argv.slice(2);
    const dry = args.includes('--dry');
    const only = args.find((a) => !a.startsWith('--'));
    const devices = only ? [only] : devicesFromCubes(CUBE_DIR);

    if (!devices.length) {
        console.log(`no device cubes in ${CUBE_DIR} — nothing to compute`);
        return;
    }
    console.log(`computing ${devices.length} forecast(s) from ${CUBE_DIR}${dry ? ' (dry run)' : ''}`);

    let ok = 0;
    for (const id of devices) {
        const t0 = Date.now();
        try {
            const input = await buildForecastInputForDevice(id);
            if (!input) { console.log(`  ${id}: insufficient telemetry, skipped`); continue; }
            const forecast = await computeMonteCarloForecast(input);
            const url = dry ? null : await storeForecast(id, forecast);
            const e = forecast.endpoint;
            console.log(
                `  ${id}: ${Date.now() - t0}ms | source ${forecast.metadata?.wind_source}` +
                ` | endpoint ${e.lat.toFixed(2)},${e.lon.toFixed(2)}` +
                (dry ? ' | (dry, not stored)' : ` | stored ${url ?? '(local)'}`),
            );
            ok++;
        } catch (err) {
            console.error(`  ${id}: FAILED ${err instanceof Error ? err.message : err}`);
        }
    }
    console.log(`done: ${ok}/${devices.length} forecast(s) computed${dry ? '' : ' + stored'}`);
}

main().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
