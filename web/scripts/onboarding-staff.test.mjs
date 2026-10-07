import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, mkdtemp, readFile, rm, stat, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArguments, runStaff } from './onboarding-staff.mjs';

const origin = 'https://stratolink.example';
const session = 'eyJ.private-session-do-not-print.signature';
const eui = '1234567890ABCDEF';
const integration = '11111111-2222-4333-8444-555555555555';
const claim = 'c'.repeat(43);

async function fixture(t, overrides = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'stratolink-staff-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const tokenFile = join(dir, 'session');
  const keyFile = join(dir, 'ttn');
  await writeFile(tokenFile, session, { mode: 0o600 });
  await writeFile(keyFile, 'NNSXS.private-test-key', { mode: 0o600 });
  const calls = [], logs = [];
  const inventory = { payloads: [{ deviceId: 'reserved-board', owned: false, devEui: eui, status: 'storage', launcherName: 'Reservation' }], integrations: [{ id: integration, cluster: 'nam1', applicationId: 'shared-app' }], ...overrides };
  const fetcher = async (url, init) => {
    calls.push({ url, ...init });
    return Response.json(init.method === 'GET' ? inventory : url.endsWith('claim-link')
      ? { deviceId: 'reserved-board', url: `${origin}/activate/reserved-board#k=${claim}`, expiresAt: '2026-10-13T00:00:00.000Z' }
      : { balloon: { id: 'reserved-board', devEui: eui } });
  };
  const common = ['--origin', origin, '--token-file', tokenFile];
  const device = ['--device', 'reserved-board', '--dev-eui', eui];
  const connection = ['--cluster', 'nam1', '--application', 'shared-app', '--integration', integration, '--ttn-key-file', keyFile];
  return { dir, tokenFile, calls, logs, fetcher, common, device, connection, log: text => logs.push(text) };
}

test('dry run fetches inventory without mutation or artifact output', async t => {
  const f = await fixture(t);
  await runStaff(['issue', ...f.common, ...f.device], f);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].method, 'GET');
  assert.equal(f.calls[0].redirect, 'error');
  assert.match(f.logs.join('\n'), /"dryRun":true/);
  assert.ok(!f.logs.join('\n').includes(session));
});

test('issue saves a private printable QR and never logs the claim token', async t => {
  const f = await fixture(t);
  const out = join(f.dir, 'label');
  await runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', out], f);
  assert.equal(f.calls.length, 2);
  assert.deepEqual(JSON.parse(f.calls[1].body), { devEui: eui });
  assert.equal((await stat(out)).mode & 0o777, 0o700);
  for (const file of ['result.json', 'claim-qr.svg', 'label.html']) assert.equal((await stat(join(out, file))).mode & 0o777, 0o600);
  assert.equal(JSON.parse(await readFile(join(out, 'result.json'), 'utf8')).url, `${origin}/activate/reserved-board#k=${claim}`);
  assert.match(await readFile(join(out, 'claim-qr.svg'), 'utf8'), /<svg/);
  assert.match(await readFile(join(out, 'label.html'), 'utf8'), /reserved-board/);
  assert.ok(!f.logs.join('\n').includes(claim));
  assert.ok(!f.logs.join('\n').includes(session));
});

test('claimed or mismatched devices cannot receive a new claim', async t => {
  for (const change of [{ owned: true }, { devEui: 'FEDCBA0987654321' }]) {
    const f = await fixture(t, { payloads: [{ deviceId: 'reserved-board', devEui: eui, ...change }] });
    await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', join(f.dir, 'label')], f), /owner|differs/);
    assert.equal(f.calls.length, 1);
  }
});

test('an owned reservation can bind a distinct regional EUI to an existing shared integration', async t => {
  const f = await fixture(t, { payloads: [{ deviceId: 'reserved-board', owned: true, devEui: 'FEDCBA0987654321' }] });
  const out = join(f.dir, 'connection');
  await runStaff(['connect', ...f.common, ...f.device, ...f.connection, '--apply', '--out', out], f);
  assert.equal(f.calls.length, 2);
  assert.equal(f.calls[1].url, `${origin}/api/staff/payloads/reserved-board/connections`);
  assert.deepEqual(JSON.parse(f.calls[1].body), { cluster: 'nam1', applicationId: 'shared-app', deviceEui: eui, apiKey: 'NNSXS.private-test-key', integrationId: integration });
  const saved = await readFile(join(out, 'result.json'), 'utf8');
  assert.ok(!saved.includes('private-test-key'));
  assert.ok(!f.logs.join('\n').includes('private-test-key'));
});

test('a mismatched shared integration stops before TTN verification', async t => {
  const f = await fixture(t, { integrations: [] });
  await assert.rejects(runStaff(['connect', ...f.common, ...f.device, ...f.connection], f), /does not match/);
  assert.equal(f.calls.length, 1);
});

test('unsafe origins and device paths fail before reading credentials', () => {
  for (const value of ['http://stratolink.example', 'https://user:pass@stratolink.example', `${origin}/dashboard`, `${origin}?key=secret`]) {
    assert.throws(() => parseArguments(['inventory', '--origin', value, '--token-file', '/private/session']), /origin/);
  }
  assert.throws(() => parseArguments(['issue', '--origin', origin, '--token-file', '/private/session', '--device', '../secret', '--dev-eui', eui]), /device/);
  assert.equal(parseArguments(['inventory', '--origin', 'http://127.0.0.1:4173', '--token-file', '/private/session']).origin, 'http://127.0.0.1:4173');
});

test('public or symlinked credential files are refused without requests', async t => {
  const f = await fixture(t);
  await chmod(f.tokenFile, 0o644);
  await assert.rejects(runStaff(['inventory', ...f.common], f), /mode 600/);
  await chmod(f.tokenFile, 0o600);
  const link = join(f.dir, 'session-link');
  await symlink(f.tokenFile, link);
  await assert.rejects(runStaff(['inventory', '--origin', origin, '--token-file', link], f), /mode 600/);
  assert.equal(f.calls.length, 0);
});

test('existing output directories are refused before POST', async t => {
  const f = await fixture(t);
  await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', f.dir], f), /must be new/);
  assert.equal(f.calls.length, 1);
});

test('artifacts cannot be saved inside the tracked project', async t => {
  const f = await fixture(t);
  const out = fileURLToPath(new URL('../private-claim-output', import.meta.url));
  await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', out], f), /outside the repository/);
  assert.equal(f.calls.length, 1);
});

test('unexpected claim origins are saved privately but never printed as a QR', async t => {
  const f = await fixture(t);
  const out = join(f.dir, 'claim');
  const fetcher = async (url, init) => init.method === 'GET' ? f.fetcher(url, init) : Response.json({ deviceId: 'reserved-board', url: `https://other.example/activate/reserved-board#k=${claim}`, expiresAt: '2026-10-13T00:00:00.000Z' });
  await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', out], { ...f, fetcher }), /check the activation URL/);
  assert.ok((await readFile(join(out, 'result.json'), 'utf8')).includes(claim));
  await assert.rejects(stat(join(out, 'claim-qr.svg')), { code: 'ENOENT' });
  assert.ok(!f.logs.join('\n').includes(claim));
});

test('new QR output rejects query credentials, duplicate proofs, and malformed credentials', async t => {
  for (const suffix of [`?k=${claim}`, `?tracking=1#k=${claim}`, `#k=${claim}&k=${claim}`, `#k=${claim}&other=1`, '#k=short']) {
    const f = await fixture(t);
    const out = join(f.dir, 'claim');
    const fetcher = async (url, init) => init.method === 'GET' ? f.fetcher(url, init) : Response.json({ deviceId: 'reserved-board', url: `${origin}/activate/reserved-board${suffix}`, expiresAt: '2026-10-13T00:00:00.000Z' });
    await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', out], { ...f, fetcher }), /check the activation URL/);
    await assert.rejects(stat(join(out, 'claim-qr.svg')), { code: 'ENOENT' });
    assert.ok(!f.logs.join('\n').includes(claim));
  }
});

test('error response details cannot leak credentials and no write is retried', async t => {
  const f = await fixture(t);
  const fetcher = async (url, init) => init.method === 'GET' ? f.fetcher(url, init) : (f.calls.push({ url, ...init }), Response.json({ error: session }, { status: 500 }));
  await assert.rejects(runStaff(['issue', ...f.common, ...f.device, '--apply', '--out', join(f.dir, 'label')], { ...f, fetcher }), error => error.message.includes('HTTP 500') && !error.message.includes(session));
  assert.equal(f.calls.length, 2);
});
