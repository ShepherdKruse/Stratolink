#!/usr/bin/env node
/**
 * Forecast worker job summary.
 *
 * Turns the activity plan (scripts/plan_forecasts.ts) and the ingest manifest
 * (appended by gfs/gefs/aigefs_ingest.py and compute_forecasts.ts) into:
 *   - a Markdown report appended to $GITHUB_STEP_SUMMARY (stdout when unset) and
 *     written to SUMMARY_FILE (default .windcube/summary.md) — member counts per
 *     source and device, step durations, what was skipped and why;
 *   - `degraded=true|false` in $GITHUB_OUTPUT, which the healthcheck step turns
 *     into a `/fail` ping. Degraded = an ingest step failed or was killed at its
 *     timeout, or any source built fewer members than configured, or a planned
 *     device was not computed.
 *
 * Env: FORECAST_PLAN, FORECAST_MANIFEST, SUMMARY_FILE, STEP_OUTCOMES (JSON
 *      {stepId: outcome} from the workflow), GITHUB_STEP_SUMMARY, GITHUB_OUTPUT.
 */
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

const SOURCES = [
  { id: 'plan', label: 'Plan' },
  { id: 'gfs', label: 'GFS cubes' },
  { id: 'gefs', label: 'GEFS members' },
  { id: 'aigefs', label: 'AIGEFS members' },
  { id: 'compute', label: 'Compute + store' },
];

function readJson(path) {
  try { return JSON.parse(readFileSync(path, 'utf8')); } catch { return null; }
}

const fmtDuration = (s) => {
  if (!Number.isFinite(s)) return '—';
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(Math.round(s % 60)).padStart(2, '0')}s` : `${Math.round(s)}s`;
};
const fmtAge = (h) => (h == null ? '—' : h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`);
const cell = (v) => String(v ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');

/** Pure: {markdown, degraded, reasons} from the run's artifacts. */
export function buildSummary({ plan = null, manifest = null, outcomes = {}, now = Date.now() } = {}) {
  const reasons = [];
  const sources = manifest?.sources ?? {};
  const devices = plan?.devices ?? [];
  const planned = devices.filter((d) => d.action === 'build').map((d) => d.device_id);

  for (const { id, label } of SOURCES) {
    const outcome = outcomes[id];
    if (outcome && outcome !== 'success' && outcome !== 'skipped') reasons.push(`${label} step outcome: ${outcome}`);
    const src = sources[id];
    if (src?.started_at && !src.finished_at) reasons.push(`${label} step did not finish (killed at its timeout?)`);
    for (const [dev, rec] of Object.entries(src?.devices ?? {})) {
      if (rec?.error) reasons.push(`${label}: ${dev} — ${rec.error}`);
      if (typeof rec?.built === 'number' && typeof rec?.expected === 'number' && rec.built < rec.expected) {
        reasons.push(`${label}: ${dev} built ${rec.built}/${rec.expected} members`);
      }
    }
  }
  /* A planned device every ensemble source skipped entirely (step killed before
   * reaching it) has no per-device record: count that too. */
  for (const id of ['gefs', 'aigefs']) {
    const src = sources[id];
    if (!src?.started_at) continue;
    for (const dev of planned) {
      if (!src.devices?.[dev]) reasons.push(`${id.toUpperCase()}: ${dev} — no members built`);
    }
  }
  const compute = sources.compute;
  if (compute?.started_at) {
    for (const dev of planned) {
      const rec = compute.devices?.[dev];
      if (!rec) reasons.push(`Compute: ${dev} — not computed`);
      else if (rec.complete === false && !rec.error) reasons.push(`Compute: ${dev} — ensemble incomplete`);
    }
  }
  const degraded = reasons.length > 0;

  const lines = [];
  lines.push(`## Forecast worker — ${new Date(now).toISOString().replace('T', ' ').slice(0, 16)} UTC`);
  lines.push('');
  lines.push(degraded ? `**Status: DEGRADED** — ${reasons.length} issue(s)` : '**Status: OK**');
  if (degraded) for (const r of [...new Set(reasons)]) lines.push(`- ${r}`);
  lines.push('');

  lines.push(`### Plan${plan ? ` — ${devices.length} device(s): ${planned.length} build, ${devices.length - planned.length} skip` : ' — no plan file'}`);
  if (plan?.requested_device) lines.push(`Requested device: \`${plan.requested_device}\`${plan.force ? ' (forced)' : ''}`);
  if (devices.length) {
    lines.push('');
    lines.push('| Device | Action | Origin fix | Age | Fixes | Reason |');
    lines.push('|---|---|---|---|---|---|');
    for (const d of devices) {
      lines.push(`| ${cell(d.device_id)} | ${d.action} | ${cell(d.origin_utc ?? '—')} | ${fmtAge(d.origin_age_h)} | ${d.n_fixes ?? '—'} | ${cell(d.reason)} |`);
    }
  }
  lines.push('');

  lines.push('### Steps');
  lines.push('');
  lines.push('| Step | Outcome | Duration | Detail |');
  lines.push('|---|---|---|---|');
  for (const { id, label } of SOURCES) {
    const src = sources[id];
    let duration = '—';
    if (src?.started_at) {
      if (src.finished_at) duration = fmtDuration(src.seconds ?? (Date.parse(src.finished_at) - Date.parse(src.started_at)) / 1000);
      else duration = `${fmtDuration((now - Date.parse(src.started_at)) / 1000)} (not finished)`;
    }
    const detail = Object.entries(src?.devices ?? {}).map(([dev, rec]) => {
      if (rec?.error) return `${dev}: FAILED ${rec.error}`;
      if (id === 'gfs') {
        const parts = [rec.fc ? 'tube' : null, rec.recon ? 'recon' : 'no recon', rec.n_fixes != null ? `${rec.n_fixes} fixes` : null].filter(Boolean);
        return `${dev}: ${parts.join(', ')}${rec.seconds != null ? ` (${fmtDuration(rec.seconds)})` : ''}`;
      }
      if (id === 'compute') {
        const m = rec.members ?? {};
        const e = rec.members_expected ?? {};
        const ens = Object.keys(m).map((k) => `${k} ${m[k]}/${e[k] ?? '?'}`).join(', ');
        return `${dev}: ${rec.n_ensemble ?? '?'} members (${ens})${rec.stored ? ', stored' : ''}${rec.complete === false ? ' — INCOMPLETE' : ''}`;
      }
      return `${dev}: ${rec.built ?? 0}/${rec.expected ?? src?.members_expected ?? '?'}${rec.seconds != null ? ` (${fmtDuration(rec.seconds)})` : ''}`;
    });
    lines.push(`| ${label} | ${outcomes[id] ?? (src ? (src.finished_at ? 'finished' : 'started') : '—')} | ${duration} | ${cell(detail.join('; ')) || '—'} |`);
  }
  lines.push('');
  return { markdown: lines.join('\n'), degraded, reasons };
}

export function main(env = process.env) {
  const planPath = env.FORECAST_PLAN ?? join(process.cwd(), '.windcube', 'plan.json');
  const manifestPath = env.FORECAST_MANIFEST ?? join(process.cwd(), '.windcube', 'manifest.json');
  const summaryFile = env.SUMMARY_FILE ?? join(process.cwd(), '.windcube', 'summary.md');
  let outcomes = {};
  try { outcomes = JSON.parse(env.STEP_OUTCOMES || '{}'); } catch { outcomes = {}; }

  const { markdown, degraded, reasons } = buildSummary({ plan: readJson(planPath), manifest: readJson(manifestPath), outcomes });
  mkdirSync(dirname(summaryFile), { recursive: true });
  writeFileSync(summaryFile, markdown);
  if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, `${markdown}\n`);
  else process.stdout.write(`${markdown}\n`);
  if (env.GITHUB_OUTPUT) appendFileSync(env.GITHUB_OUTPUT, `degraded=${degraded}\n`);
  console.log(degraded ? `degraded: ${reasons.join('; ')}` : 'run complete, not degraded');
  return degraded;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
