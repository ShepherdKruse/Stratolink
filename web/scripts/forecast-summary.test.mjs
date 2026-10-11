import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildSummary, main } from './forecast_summary.mjs';

const t0 = Date.parse('2026-10-10T17:00:00Z');
const iso = (m) => new Date(t0 + m * 60_000).toISOString();
const plan = { version: 1, generated_at: iso(0), requested_device: null, force: false, devices: [
  { device_id: 'live', action: 'build', reason: 'last fix 3.2 h ago — forecast still evolves', origin_utc: iso(-192), origin_age_h: 3.2, n_fixes: 812 },
  { device_id: 'dark', action: 'skip', reason: 'frozen: stored forecast is already the final dead-reckon', origin_utc: iso(-100000), origin_age_h: 1700, n_fixes: 0 },
] };
const ok = { version: 1, sources: {
  gfs: { started_at: iso(1), finished_at: iso(8), seconds: 420, devices: { live: { fc: true, recon: true, n_fixes: 812, seconds: 418 } } },
  gefs: { started_at: iso(8), finished_at: iso(23), seconds: 900, members_expected: 31, devices: { live: { built: 31, expected: 31, seconds: 880 } } },
  aigefs: { started_at: iso(23), finished_at: iso(41), seconds: 1080, members_expected: 31, devices: { live: { built: 31, expected: 31, seconds: 1070 } } },
  compute: { started_at: iso(41), finished_at: iso(42), seconds: 61, devices: { live: { n_ensemble: 62, members: { gefs: 31, aigefs: 31 }, members_expected: { gefs: 31, aigefs: 31 }, complete: true, stored: true, seconds: 60 } } },
} };
const outcomes = { plan: 'success', gfs: 'success', gefs: 'success', aigefs: 'success', compute: 'success' };

test('a complete run is not degraded and lists counts, durations and skip reasons', () => {
  const s = buildSummary({ plan, manifest: ok, outcomes, now: t0 + 43 * 60_000 });
  assert.equal(s.degraded, false);
  assert.match(s.markdown, /Status: OK/);
  assert.match(s.markdown, /\| live \| build \|/);
  assert.match(s.markdown, /\| dark \| skip \| .* frozen: stored forecast is already the final dead-reckon \|/);
  assert.match(s.markdown, /\| GEFS members \| success \| 15m 00s \| live: 31\/31 \(14m 40s\) \|/);
  assert.match(s.markdown, /\| Compute \+ store \| success \| 1m 01s \| live: 62 members \(gefs 31\/31, aigefs 31\/31\), stored \|/);
});

test('fewer members than configured, a killed step and a failed outcome all degrade the run', () => {
  const manifest = structuredClone(ok);
  manifest.sources.aigefs = { started_at: iso(23), members_expected: 31, devices: { live: { built: 23, expected: 31 } } }; // no finished_at
  manifest.sources.compute.devices.live.members = { gefs: 31, aigefs: 23 };
  manifest.sources.compute.devices.live.complete = false;
  const s = buildSummary({ plan, manifest, outcomes: { ...outcomes, aigefs: 'failure' }, now: t0 + 50 * 60_000 });
  assert.equal(s.degraded, true);
  assert.match(s.markdown, /Status: DEGRADED/);
  assert.ok(s.reasons.some((r) => /AIGEFS members step outcome: failure/.test(r)), s.reasons.join('|'));
  assert.ok(s.reasons.some((r) => /did not finish/.test(r)), s.reasons.join('|'));
  assert.ok(s.reasons.some((r) => /live built 23\/31 members/.test(r)), s.reasons.join('|'));
  assert.match(s.markdown, /\| AIGEFS members \| failure \| 27m 00s \(not finished\) \| live: 23\/31 \|/);
});

test('a planned device the ensemble step never reached is reported', () => {
  const manifest = structuredClone(ok);
  manifest.sources.gefs = { started_at: iso(8), members_expected: 31, devices: {} };   // killed before `live`
  const s = buildSummary({ plan, manifest, outcomes: { ...outcomes, gefs: 'failure' }, now: t0 + 50 * 60_000 });
  assert.ok(s.reasons.some((r) => /GEFS: live — no members built/.test(r)), s.reasons.join('|'));
  delete manifest.sources.compute.devices.live;
  const s2 = buildSummary({ plan, manifest, outcomes, now: t0 + 50 * 60_000 });
  assert.ok(s2.reasons.some((r) => /Compute: live — not computed/.test(r)), s2.reasons.join('|'));
});

test('a run with nothing to build (or no files at all) renders and is not degraded', () => {
  const empty = { ...plan, devices: [plan.devices[1]] };
  const manifest = { version: 1, sources: {
    gfs: { started_at: iso(1), finished_at: iso(1), seconds: 0, devices: {} },
    gefs: { started_at: iso(1), finished_at: iso(1), seconds: 0, members_expected: 31, devices: {} },
    aigefs: { started_at: iso(1), finished_at: iso(1), seconds: 0, members_expected: 31, devices: {} },
    compute: { started_at: iso(1), finished_at: iso(1), seconds: 0, devices: {} },
  } };
  assert.equal(buildSummary({ plan: empty, manifest, outcomes, now: t0 }).degraded, false);
  const bare = buildSummary({});
  assert.equal(bare.degraded, false);
  assert.match(bare.markdown, /no plan file/);
});

test('main writes the summary file, the step summary and the degraded output', () => {
  const dir = mkdtempSync(join(tmpdir(), 'stratolink-summary-'));
  try {
    const manifest = structuredClone(ok);
    manifest.sources.gefs.devices.live.built = 17;
    writeFileSync(join(dir, 'plan.json'), JSON.stringify(plan));
    writeFileSync(join(dir, 'manifest.json'), JSON.stringify(manifest));
    const env = { FORECAST_PLAN: join(dir, 'plan.json'), FORECAST_MANIFEST: join(dir, 'manifest.json'),
      SUMMARY_FILE: join(dir, 'out', 'summary.md'), GITHUB_STEP_SUMMARY: join(dir, 'step.md'),
      GITHUB_OUTPUT: join(dir, 'output.txt'), STEP_OUTCOMES: JSON.stringify(outcomes) };
    assert.equal(main(env), true);
    assert.match(readFileSync(join(dir, 'out', 'summary.md'), 'utf8'), /live built 17\/31 members/);
    assert.match(readFileSync(join(dir, 'step.md'), 'utf8'), /Status: DEGRADED/);
    assert.equal(readFileSync(join(dir, 'output.txt'), 'utf8'), 'degraded=true\n');
  } finally { rmSync(dir, { recursive: true }); }
});
