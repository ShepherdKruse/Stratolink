/**
 * Local forecast iteration harness — NO production writes.
 *
 * Reads wind cubes from WIND_CUBE_DIR (default .windcube/cubes), builds the input
 * from Supabase (read-only) the first time and caches it to /tmp, runs
 * computeMonteCarloForecast, and dumps the result to /tmp/forecast_local.json.
 * Blob is disabled so the reconstruction/forecast caches stay in .forecast-cache
 * and nothing touches prod.
 *
 *   npx tsx scripts/forecast_local.ts [deviceId] [--offline]
 *     --offline  reuse the cached input (no Supabase call)
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const envPath = join(process.cwd(), '.env.local');
if (existsSync(envPath)) {
    for (const line of readFileSync(envPath, 'utf8').split('\n')) {
        const m = line.match(/^([A-Z_]+)=(.*)$/);
        if (m) process.env[m[1]] = m[2].replace(/^"|"$/g, '');
    }
}
// Local-only: forecast + hindcast caches go to .forecast-cache, never prod Blob.
delete process.env.BLOB_READ_WRITE_TOKEN;
delete process.env.BLOB_STORE_ID;
process.env.WIND_CUBE_DIR = process.env.WIND_CUBE_DIR ?? join(process.cwd(), '.windcube', 'cubes');

async function main() {
    const device = process.argv.slice(2).find((a) => !a.startsWith('--')) ?? 'stratolink-3';
    const offline = process.argv.includes('--offline');
    const inputCache = join('/tmp', `fc_input_${device}.json`);

    const { buildForecastInputForDevice } = await import('@/lib/wind/buildForecastInput');
    const { computeMonteCarloForecast } = await import('@/lib/wind/monteCarloForecast');

    let input;
    if (offline && existsSync(inputCache)) {
        input = JSON.parse(readFileSync(inputCache, 'utf8'));
        console.log('loaded cached input:', inputCache, '— fixes:', input.gpsFixes?.length);
    } else {
        input = await buildForecastInputForDevice(device);
        if (!input) { console.error('no input for', device); process.exit(1); }
        writeFileSync(inputCache, JSON.stringify(input));
        console.log('built input (cached):', inputCache, '— fixes:', input.gpsFixes.length, 'pressureHpa:', input.pressureHpa);
    }

    const t0 = Date.now();
    const fc = await computeMonteCarloForecast(input);
    console.log('computed in', ((Date.now() - t0) / 1000).toFixed(1) + 's', '| wind_source:', fc.metadata?.wind_source, '| stale gap_h:', fc.stale_gps?.gap_hours);
    writeFileSync('/tmp/forecast_local.json', JSON.stringify(fc));
    console.log('wrote /tmp/forecast_local.json');
}

main().catch((e) => { console.error(e); process.exit(1); });
