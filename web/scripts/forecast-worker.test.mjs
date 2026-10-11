import assert from 'node:assert/strict';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = new URL('../', import.meta.url);
const webPath = (relative) => fileURLToPath(new URL(relative, web));
const tsxCli = webPath('node_modules/tsx/dist/cli.mjs');
/** Mirrors the scripts/gfs_ingest.py `.slwc` v1 packer (see windCube.ts cubeFromBinary):
 *  one static box, uniform eastward wind with a mild time evolution. */
function packCube({ t0Ms, stepMs, nGrids, lat0 = 20, lon0 = -140, step = 1, nLat = 51, nLon = 61, u = 15, v = 2 }) {
  const header = { v: 1, scale: 10, t0Ms, stepMs, gridStep: step, levelHpa: 280, source: 'gfs', generated_at: new Date(t0Ms).toISOString(),
    bounds: { latMin: lat0, latMax: lat0 + (nLat - 1) * step, lonMin: lon0, lonMax: lon0 + (nLon - 1) * step },
    lat0, dLat: step, nLat, lon0, dLon: step, nLon, nGrids };
  const json = Buffer.from(JSON.stringify(header), 'utf8');
  const headerLen = Math.ceil(json.length / 4) * 4;
  const n = nLat * nLon;
  const buf = Buffer.alloc(4 + headerLen + nGrids * n * 4);
  buf.writeUInt32LE(headerLen, 0);
  json.copy(buf, 4);
  buf.fill(0x20, 4 + json.length, 4 + headerLen); // pad with JSON whitespace, as the Python writer does
  let offset = 4 + headerLen;
  for (let g = 0; g < nGrids; g++) {
    const ug = Math.round((u + Math.sin(g / 7) * 3) * 10), vg = Math.round((v + Math.cos(g / 11) * 2) * 10);
    for (let i = 0; i < n; i++) { buf.writeInt16LE(ug, offset); offset += 2; }
    for (let i = 0; i < n; i++) { buf.writeInt16LE(vg, offset); offset += 2; }
  }
  return buf;
}

function run(args) {
  const cubes = mkdtempSync(join(tmpdir(), 'stratolink-worker-'));
  try {
    return spawnSync(process.execPath, ['--import', 'tsx', 'scripts/compute_forecasts.ts', ...args], {
      cwd: new URL('../', import.meta.url), encoding: 'utf8', timeout: 15000,
      env: { ...process.env, TSX_TSCONFIG_PATH: 'tsconfig.worker.json', WIND_CUBE_DIR: cubes,
        SUPABASE_URL: '', NEXT_PUBLIC_SUPABASE_URL: '', SUPABASE_SERVER_KEY: '', SUPABASE_SERVICE_ROLE_KEY: '', BLOB_READ_WRITE_TOKEN: '' },
    });
  } finally { rmSync(cubes, { recursive: true }); }
}

test('worker handles an empty fleet without touching external services', () => {
  const result = run([]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /no device cubes/);
});

test('worker rejects malformed and unknown CLI options', () => {
  for (const args of [['../../secret'], ['--unsafe'], ['one', 'two']]) {
    const result = run(args);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /Invalid forecast device argument/);
  }
});

test('requested device with no ingested cube fails instead of running an unbounded fallback', () => {
  const result = run(['stratolink-3']);
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /No ingested cube/);
});

test('a device with no ingested cube fails the cube read clearly instead of fetching live weather', () => {
  const dir = mkdtempSync(join(tmpdir(), 'stratolink-nocube-'));
  try {
    writeFileSync(join(dir, 'read.mts'), `import { fetchWindCube } from ${JSON.stringify(webPath('lib/wind/windCube.ts'))};\nawait fetchWindCube({ deviceId: 'stratolink-9', kind: 'forecast' });\n`);
    const result = spawnSync(process.execPath, [tsxCli, join(dir, 'read.mts')], {
      cwd: dir, encoding: 'utf8', timeout: 15000,
      env: { ...process.env, WIND_CUBE_DIR: dir, BLOB_READ_WRITE_TOKEN: '' },
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /No forecast wind cube for device "stratolink-9" \(looked in WIND_CUBE_DIR=.*, Blob \(not configured\)\)/);
    assert.match(result.stderr, /no live weather fallback/);
  } finally { rmSync(dir, { recursive: true }); }
});

test('the offline harness computes from local cubes and stores no wind grid or gap geometry', () => {
  const dir = mkdtempSync(join(tmpdir(), 'stratolink-local-'));
  try {
    const cubes = join(dir, 'cubes');
    mkdirSync(cubes);
    const hour = 3_600_000, now = Math.floor(Date.now() / hour) * hour;
    writeFileSync(join(cubes, 'stratolink-9.slwc'), packCube({ t0Ms: now - 10 * 24 * hour, stepMs: 3 * hour, nGrids: 112 }));
    writeFileSync(join(cubes, 'stratolink-9-fc.slwc'), packCube({ t0Ms: now - 3 * 24 * hour, stepMs: hour, nGrids: 120 }));
    // 24 h of fixes drifting east, an 8 h hole (long-gap corridor reconstruction), last fix 2 h ago (stale GPS).
    const fixes = [];
    for (let h = 0; h <= 24; h += 2) {
      if (h > 8 && h < 16) continue;
      fixes.push({ lat: 40 + 0.05 * h, lon: -125 + 0.6 * h, time_utc: new Date(now - 26 * hour + h * hour).toISOString(), alt_m: 9500 });
    }
    writeFileSync(join(dir, 'fc_input_stratolink-9.json'), JSON.stringify({
      deviceId: 'stratolink-9', mission: 'synthetic', launch: { lat: 40, lon: -125, time_utc: fixes[0].time_utc },
      gpsFixes: fixes, observedTrackLonLat: fixes.map(fix => [fix.lon, fix.lat]), pressureHpa: 280, forecastHours: 24, nEnsemble: 40,
    }));
    const result = spawnSync(process.execPath, [tsxCli, '--tsconfig', webPath('tsconfig.worker.json'), webPath('scripts/forecast_local.ts'), 'stratolink-9', '--offline'], {
      cwd: dir, encoding: 'utf8', timeout: 120000,
      env: { ...process.env, FORECAST_LOCAL_DIR: dir, WIND_CUBE_DIR: cubes, BLOB_READ_WRITE_TOKEN: 'must-be-dropped',
        SUPABASE_URL: '', NEXT_PUBLIC_SUPABASE_URL: '', SUPABASE_SERVER_KEY: '', SUPABASE_SERVICE_ROLE_KEY: '' },
    });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /wind_source: gfs/);
    const forecast = JSON.parse(readFileSync(join(dir, 'forecast_local.json'), 'utf8'));
    assert.equal(forecast.metadata.wind_source, 'gfs');
    assert.equal(forecast.metadata.n_ensemble, 40);
    assert.ok(forecast.nominal_path.length >= 2);
    assert.equal(forecast.stale_gps.wind_mode, 'gfs_cube');
    assert.equal('wind_field' in forecast, false);
    const gaps = forecast.observed.reconstruction_gaps;
    assert.ok(gaps.some(gap => gap.dt_hours >= 8), 'the long gap was reconstructed');
    for (const gap of gaps) {
      assert.equal('occupancy' in gap, false);
      assert.equal('ellipses' in gap, false);
      assert.equal(typeof gap.confidence, 'string');
    }
    assert.ok(readFileSync(join(dir, '.forecast-cache', 'stratolink-9.gapcache.json'), 'utf8').length > 2, 'caches stayed local');
  } finally { rmSync(dir, { recursive: true }); }
});
