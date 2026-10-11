import assert from 'node:assert/strict';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tsImport } from 'tsx/esm/api';

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

/** Spawn the worker CLI with an isolated cube dir; `plan` (object) is written as
 *  its plan file, otherwise the plan path points at a file that does not exist. */
function run(args, { plan = null, script = 'scripts/compute_forecasts.ts' } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'stratolink-worker-'));
  const planPath = join(dir, 'plan.json');
  if (plan) writeFileSync(planPath, JSON.stringify(plan));
  try {
    return spawnSync(process.execPath, ['--import', 'tsx', script, ...args], {
      cwd: new URL('../', import.meta.url), encoding: 'utf8', timeout: 20000,
      env: { ...process.env, TSX_TSCONFIG_PATH: 'tsconfig.worker.json', WIND_CUBE_DIR: join(dir, 'cubes'),
        FORECAST_PLAN: planPath, FORECAST_MANIFEST: join(dir, 'manifest.json'), FORCE: '',
        SUPABASE_URL: '', NEXT_PUBLIC_SUPABASE_URL: '', SUPABASE_SERVER_KEY: '', SUPABASE_SERVICE_ROLE_KEY: '', BLOB_READ_WRITE_TOKEN: '' },
    });
  } finally { rmSync(dir, { recursive: true }); }
}

const freshPlan = (devices) => ({ version: 1, generated_at: new Date().toISOString(), devices });

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

test('worker follows the plan: skipped devices are not computed, even by name', () => {
  const plan = freshPlan([{ device_id: 'dark', action: 'skip', reason: 'frozen: final dead-reckon stored' }]);
  let result = run([], { plan });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /no devices to build/);
  /* Requested by name: the ingest steps were no-ops for it, so is the compute. */
  result = run(['dark'], { plan });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /dark: skipped by plan — frozen/);
  /* Not in the plan at all (and no cube): an error, as without a plan. */
  result = run(['ghost'], { plan });
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /No planned build for the requested device/);
});

test('worker ignores a stale plan and falls back to the cubes on disk', () => {
  const plan = { version: 1, generated_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    devices: [{ device_id: 'ghost', action: 'build' }] };
  const result = run([], { plan });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /ignoring stale plan/);
  assert.match(result.stdout, /no device cubes/);
});

test('plan step rejects malformed device arguments and refuses to run without a database', () => {
  for (const args of [['../../secret'], ['one', 'two']]) {
    const result = run(args, { script: 'scripts/plan_forecasts.ts' });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /Invalid forecast device argument/);
  }
  const result = run([], { script: 'scripts/plan_forecasts.ts' });
  assert.equal(result.status, 1, result.stderr);
  assert.match(result.stderr, /not configured/);
});

/* ── Activity-gate rules (lib/wind/forecastPlan.ts) ──────────────────────── */
const { decideDevice, storedForecastSummary, planIsFresh, planConfigFromEnv, FREEZE_MARGIN_H } =
  await tsImport('../lib/wind/forecastPlan.ts', import.meta.url);

const H = 3_600_000;
const cfg = { horizonH: 24, deadReckonCapH: 14 * 24, freezeMarginH: 24 };
const now = Date.parse('2026-10-10T18:00:00Z');
const at = (hoursAgo) => new Date(now - hoursAgo * H).toISOString();
const device = (over) => ({
  deviceId: 'd', launchedAt: at(500), lastFixUtc: at(10), nFixes: 42, hasLaunchRecord: true, stored: null, ...over,
});

test('active balloon is always built', () => {
  assert.equal(decideDevice(device(), cfg, now).action, 'build');
  const dark = decideDevice(device({ lastFixUtc: at(300) }), cfg, now);   // inside the 14 d cap
  assert.equal(dark.action, 'build');
  assert.match(dark.reason, /still evolves/);
});

test('past the cap but within the publication-lag margin still rebuilds', () => {
  const d = decideDevice(device({ lastFixUtc: at(14 * 24 + 6), stored: { generated_at: at(1), last_fix_utc: at(14 * 24 + 6) } }), cfg, now);
  assert.equal(d.action, 'build');
  assert.match(d.reason, /not final/);
});

test('frozen balloon with its final forecast stored is skipped', () => {
  const lastFix = at(71 * 24);
  const d = decideDevice(device({ lastFixUtc: lastFix, stored: { generated_at: at(4 * 24), last_fix_utc: lastFix } }), cfg, now);
  assert.equal(d.action, 'skip');
  assert.match(d.reason, /^frozen/);
  assert.equal(d.origin_utc, lastFix);
  assert.equal(d.origin_age_h, 71 * 24);
});

test('frozen balloon is rebuilt when no final forecast exists yet', () => {
  const lastFix = at(20 * 24);
  assert.equal(decideDevice(device({ lastFixUtc: lastFix }), cfg, now).action, 'build');
  /* Stored, but generated before every tube field became immutable (cap + margin). */
  const early = decideDevice(device({ lastFixUtc: lastFix, stored: { generated_at: at(20 * 24 - 14 * 24 - 2), last_fix_utc: lastFix } }), cfg, now);
  assert.equal(early.action, 'build');
  assert.match(early.reason, /predates/);
  /* Generated after cap + margin ⇒ final. */
  const final = decideDevice(device({ lastFixUtc: lastFix, stored: { generated_at: at(20 * 24 - 15 * 24 - 1), last_fix_utc: lastFix } }), cfg, now);
  assert.equal(final.action, 'skip');
  /* Exactly one FREEZE_MARGIN_H past the cap is the boundary. */
  assert.equal(FREEZE_MARGIN_H, 24);
});

test('a stored forecast from a different fix never freezes the device', () => {
  const lastFix = at(30 * 24);
  const d = decideDevice(device({ lastFixUtc: lastFix, stored: { generated_at: at(1), last_fix_utc: at(31 * 24) } }), cfg, now);
  assert.equal(d.action, 'build');
  assert.match(d.reason, /starts from/);
});

test('launch-record-only balloon uses the launch time as its origin', () => {
  const launch = at(16 * 24);
  const build = decideDevice(device({ nFixes: 0, lastFixUtc: null, launchedAt: launch }), cfg, now);
  assert.equal(build.action, 'build');
  assert.equal(build.origin_utc, launch);
  const frozen = decideDevice(device({ nFixes: 0, lastFixUtc: null, launchedAt: launch, stored: { generated_at: at(12), last_fix_utc: launch } }), cfg, now);
  assert.equal(frozen.action, 'skip');
});

test('nothing to start from is skipped', () => {
  const d = decideDevice(device({ nFixes: 0, lastFixUtc: null, hasLaunchRecord: false, launchedAt: null }), cfg, now);
  assert.equal(d.action, 'skip');
  assert.match(d.reason, /no GPS fixes .* no launch record/);
  assert.equal(d.origin_utc, null);
});

test('force rebuilds a frozen balloon but not one with nothing to start from', () => {
  const lastFix = at(71 * 24);
  const forced = decideDevice(device({ lastFixUtc: lastFix, stored: { generated_at: at(4 * 24), last_fix_utc: lastFix }, force: true }), cfg, now);
  assert.equal(forced.action, 'build');
  assert.match(forced.reason, /forced/);
  const empty = decideDevice(device({ nFixes: 0, lastFixUtc: null, hasLaunchRecord: false, launchedAt: null, force: true }), cfg, now);
  assert.equal(empty.action, 'skip');
});

test('stored forecast summary reads the last observed fix (launch pseudo-fix included)', () => {
  assert.equal(storedForecastSummary(null), null);
  assert.deepEqual(
    storedForecastSummary({ generated_at: 'g', observed: { gps_fixes: [{ time_utc: 'a' }, { time_utc: 'b' }] } }),
    { generated_at: 'g', last_fix_utc: 'b' },
  );
  assert.deepEqual(
    storedForecastSummary({ generated_at: 'g', observed: { gps_fixes: [] }, stale_gps: { last_fix_time_utc: 's' } }),
    { generated_at: 'g', last_fix_utc: 's' },
  );
});

test('plan config mirrors the ingest env and plans go stale after 12 h', () => {
  assert.equal(planConfigFromEnv({}).deadReckonCapH, 14 * 24);
  assert.equal(planConfigFromEnv({ FC_DEAD_RECKON_CAP_H: '48' }).deadReckonCapH, 48);
  assert.equal(planConfigFromEnv({ FC_DEAD_RECKON_CAP_H: 'junk' }).deadReckonCapH, 14 * 24);
  assert.equal(planIsFresh({ generated_at: at(1) }, now), true);
  assert.equal(planIsFresh({ generated_at: at(13) }, now), false);
  assert.equal(planIsFresh(null, now), false);
});

/* ── Ingest manifest → forecast metadata (lib/wind/forecastManifest.ts) ──── */
const { ensembleMembers, formatMembers } = await tsImport('../lib/wind/forecastManifest.ts', import.meta.url);

test('member counts come from the cubes on disk, expectations from the manifest', () => {
  const labels = [...Array(31).keys()].map((i) => `m${String(i).padStart(2, '0')}`)
    .concat([...Array(23).keys()].map((i) => `a${String(i).padStart(2, '0')}`));
  const manifest = { version: 1, sources: {
    gefs: { members_expected: 31, devices: { d: { built: 31, expected: 31 } } },
    aigefs: { members_expected: 31, devices: { d: { built: 23, expected: 31 } } },   // killed at 23
  } };
  const m = ensembleMembers(labels, manifest, 'd');
  assert.deepEqual(m.members, { gefs: 31, aigefs: 23 });
  assert.deepEqual(m.expected, { gefs: 31, aigefs: 31 });
  assert.equal(m.complete, false);
  assert.equal(formatMembers(m), 'gefs 31/31, aigefs 23/31');
  /* Source never recorded the device (step killed before it): the source-level
   * expectation still applies. */
  const none = ensembleMembers(labels.slice(0, 31), { version: 1, sources: { gefs: { members_expected: 31, devices: { d: { built: 31, expected: 31 } } }, aigefs: { members_expected: 31, devices: {} } } }, 'd');
  assert.deepEqual(none.expected, { gefs: 31, aigefs: 31 });
  assert.equal(none.complete, false);
  /* Complete run. */
  const full = ensembleMembers(labels.concat([...Array(8).keys()].map((i) => `a${23 + i}`)), manifest, 'd');
  assert.equal(full.members.aigefs, 31);
});

test('without a manifest the counts are still reported and the ensemble is not called complete', () => {
  const m = ensembleMembers(['m00', 'm01'], null, 'd');
  assert.deepEqual(m.members, { gefs: 2, aigefs: 0 });
  assert.deepEqual(m.expected, {});
  assert.equal(m.complete, false);
  assert.equal(formatMembers(m), 'gefs 2/?, aigefs 0/?');
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
