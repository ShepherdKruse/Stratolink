import assert from 'node:assert/strict';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

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
