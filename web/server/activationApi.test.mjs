import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createCommunityApi, verifyTTNDevice } from './communityApi.js';

const uid = '10000000-0000-4000-8000-000000000001';
const deviceId = 'stratolink-test';
const devEui = '1122334455667788';
const claimToken = 'A'.repeat(43);
const user = { id: uid, identities: [{ provider: 'github', identity_data: { sub: '12345', user_name: 'test-user' } }] };
const balloon = { id: deviceId, devEui, callsign: 'Test', connections: [] };
const integration = { id: '10000000-0000-4000-8000-000000000002', cluster: 'nam1', applicationId: 'test-app' };
const inventory = { payloads: [{ deviceId, devEui, owned: false }], integrations: [integration] };
function fixture(options = {}) {
  const calls = []; let dbCalls = 0;
  const db = {
    auth: { async getUser() { return { data: { user: options.user ?? user }, error: null }; } },
    async rpc(name, args) {
      calls.push({ name, args });
      if (options.rpc) { const result = options.rpc(name, args); if (result !== undefined) return result; }
      return { error: null, data: name === 'community_rate_limit' ? true : name === 'staff_payload_inventory' ? inventory : name === 'community_account' ? [balloon] : name === 'issue_payload_claim' ? { deviceId, expiresAt: '2026-10-20T00:00:00Z' } : balloon };
    },
  };
  const api = createCommunityApi({
    createDb() { dbCalls++; return db; },
    verifyDevice: options.verifyDevice,
    environment: { SITE_URL: 'https://stratolink.org', AUTH_ALLOWED_ORIGINS: 'https://preview.example', COMMUNITY_REGISTRATION_ENABLED: 'true', PAYLOAD_CLAIM_COOKIE_SECRET: Buffer.alloc(32, 7).toString('base64url'), PAYLOAD_STAFF_USER_IDS: uid, ...options.environment },
  });
  const request = (path, method = 'GET', body, headers = {}) => api(new Request(`http://localhost${path}`, {
    method, headers: { authorization: 'Bearer synthetic-bearer-token-for-tests', origin: 'https://stratolink.org', 'content-type': 'application/json', ...headers },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }));
  const intent = async (body = { deviceId, claimToken }) => {
    const response = await request('/api/activation/intent', 'POST', body, { authorization: '' });
    assert.equal(response.status, 200);
    return response.headers.get('set-cookie').split(';')[0];
  };
  return { request, intent, calls, get dbCalls() { return dbCalls; } };
}

test('QR intent is private, short lived, and stored without touching the database', async () => {
  const f = fixture();
  const response = await f.request('/api/activation/intent', 'POST', { deviceId, claimToken }, { authorization: '' });
  const body = await response.json();
  assert.equal(body.intent.deviceId, deviceId);
  assert.equal(body.intent.requiresProof, false);
  assert.doesNotMatch(JSON.stringify(body), /tokenHash|AAAAAAAA/);
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, /HttpOnly; SameSite=Lax; Max-Age=1800; Secure/);
  assert.doesNotMatch(cookie, new RegExp(claimToken));
  assert.equal(f.dbCalls, 0);
  const resumed = await f.request('/api/activation/intent', 'GET', undefined, { cookie: cookie.split(';')[0], authorization: '' });
  assert.deepEqual((await resumed.json()).intent, body.intent);
});

test('device-only and short legacy links retain context without accepting a PIN', async () => {
  for (const extra of [{}, { claimToken: '123456' }]) {
    const f = fixture(); const cookie = await f.intent({ deviceId, ...extra });
    const status = await f.request('/api/activation/intent', 'GET', undefined, { cookie });
    assert.equal((await status.json()).intent.requiresProof, true);
    assert.equal((await f.request('/api/activation/claim', 'POST', { deviceId }, { cookie })).status, 400);
    assert.equal(f.calls.some(call => call.name === 'claim_existing_payload'), false);
  }
});

test('only authenticated explicit confirmation claims the existing device', async () => {
  const f = fixture(); const cookie = await f.intent();
  assert.equal((await f.request('/api/activation/claim', 'POST', { deviceId }, { cookie, authorization: '' })).status, 401);
  const response = await f.request('/api/activation/claim', 'POST', { deviceId }, { cookie });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
  assert.deepEqual(f.calls.find(call => call.name === 'claim_existing_payload').args, { p_owner_id: uid, p_github_login: 'test-user', p_device_id: deviceId, p_token_hash: createHash('sha256').update(claimToken).digest('hex') });
  assert.equal(f.calls.some(call => /register_community|update_community|connect_community/.test(call.name)), false);
});

test('manual fresh proof works while invalid or expired proof retains only device context', async () => {
  const f = fixture({ rpc: name => name === 'claim_existing_payload' ? { data: null, error: null } : undefined });
  const cookie = await f.intent({ deviceId });
  const response = await f.request('/api/activation/claim', 'POST', { deviceId, claimToken }, { cookie });
  assert.equal(response.status, 409);
  const next = response.headers.get('set-cookie').split(';')[0];
  const resumed = await f.request('/api/activation/intent', 'GET', undefined, { cookie: next });
  assert.equal((await resumed.json()).intent.requiresProof, true);
});

test('cross-origin, missing, tampered and stale-tab intent cannot claim', async () => {
  const f = fixture(); const cookie = await f.intent();
  for (const [body, headers, status] of [
    [{ deviceId }, {}, 409],
    [{ deviceId }, { cookie: cookie + 'tampered' }, 409],
    [{ deviceId: 'different-payload' }, { cookie }, 409],
    [{ deviceId }, { cookie, origin: 'https://preview.example' }, 409],
    [{ deviceId }, { cookie, origin: 'https://evil.example' }, 403],
    [{ deviceId }, { cookie, 'sec-fetch-site': 'cross-site' }, 403],
    [{ deviceId, ownerId: uid }, { cookie }, 400],
  ]) assert.equal((await f.request('/api/activation/claim', 'POST', body, headers)).status, status);
  assert.equal(f.calls.some(call => call.name === 'claim_existing_payload'), false);
});

test('disabled rollout blocks every new mutation but allows intent removal and account reads', async () => {
  const f = fixture({ environment: { COMMUNITY_REGISTRATION_ENABLED: 'false' } });
  for (const path of ['/api/activation/intent','/api/activation/claim','/api/balloons/reserve',`/api/staff/payloads/${deviceId}/claim-link`,`/api/staff/payloads/${deviceId}/connections`]) assert.equal((await f.request(path, 'POST', {})).status, 503);
  assert.equal(f.dbCalls, 0);
  assert.equal((await f.request('/api/activation/intent', 'DELETE', {})).status, 200);
  assert.equal((await f.request('/api/account')).status, 200);
});

test('intent validation rejects oversized or injected fields and fails closed without a signing key', async () => {
  const f = fixture();
  for (const body of [null, [], { deviceId: '../other' }, { deviceId, ownerId: uid }, { deviceId, claimToken: 123 }, { deviceId, claimToken: 'a'.repeat(257) }]) assert.equal((await f.request('/api/activation/intent', 'POST', body)).status, 400);
  assert.equal((await f.request('/api/activation/intent', 'POST', { deviceId, claimToken: 'a'.repeat(3000) })).status, 413);
  const noKey = fixture({ environment: { PAYLOAD_CLAIM_COOKIE_SECRET: '' } });
  assert.equal((await noKey.request('/api/activation/intent', 'POST', { deviceId })).status, 503);
});

test('reservation preserves callsign IDs and legacy owner status writes', async () => {
  const f = fixture();
  const response = await f.request('/api/balloons/reserve', 'POST', { callsign: '  Test-Call  ' });
  assert.equal(response.status, 201);
  assert.deepEqual(f.calls.find(call => call.name === 'reserve_community_payload').args, { p_owner_id: uid, p_github_login: 'test-user', p_callsign: 'test-call' });
  for (const callsign of ['ab','two words','bad--id','../id','a'.repeat(37), 'a-'.repeat(25) + 'a']) assert.equal((await f.request('/api/balloons/reserve', 'POST', { callsign })).status, 400);
  assert.equal((await f.request(`/api/balloons/${deviceId}`, 'PATCH', { status: 'landed' })).status, 200);
});

test('staff role comes from verified user ID and all staff paths enforce it before RPC', async () => {
  const f = fixture({ environment: { PAYLOAD_STAFF_USER_IDS: '' }, user: { ...user, user_metadata: { role: 'admin', staff: true } } });
  for (const [path, method] of [['/api/staff/payloads','GET'],[`/api/staff/payloads/${deviceId}/claim-link`,'POST'],[`/api/staff/payloads/${deviceId}/connections`,'POST']]) assert.equal((await f.request(path, method, method === 'POST' ? {} : undefined)).status, 403);
  assert.equal(f.calls.length, 0);
});

test('staff issues a fresh hashed proof only for existing unowned inventory', async () => {
  const f = fixture();
  const response = await f.request(`/api/staff/payloads/${deviceId}/claim-link`, 'POST', { devEui });
  assert.equal(response.status, 201);
  const data = await response.json(); const url = new URL(data.url);
  assert.equal(url.origin, 'https://stratolink.org');
  assert.equal(url.pathname, `/activate/${deviceId}`);
  assert.equal(url.search, '');
  const proof = new URLSearchParams(url.hash.slice(1)).get('k');
  const call = f.calls.find(item => item.name === 'issue_payload_claim');
  assert.equal(call.args.p_issuer_id, uid);
  assert.equal(call.args.p_token_hash, createHash('sha256').update(proof).digest('hex'));
  assert.doesNotMatch(JSON.stringify(call), new RegExp(proof));
  const owned = fixture({ rpc: name => name === 'staff_payload_inventory' ? { data: { ...inventory, payloads: [{ ...inventory.payloads[0], owned: true }] }, error: null } : undefined });
  assert.equal((await owned.request(`/api/staff/payloads/${deviceId}/claim-link`, 'POST', { devEui })).status, 409);
  assert.equal(owned.calls.some(item => item.name === 'issue_payload_claim'), false);
});

test('staff verifies network before binding a shared integration and never stores TTN key', async () => {
  let verified;
  const f = fixture({ verifyDevice: async input => { verified = input; return { ...input, deviceId: 'network-device', region: 'US915' }; } });
  const input = { integrationId: integration.id, cluster: integration.cluster, applicationId: integration.applicationId, deviceEui: devEui, apiKey: 'synthetic-ttn-key-not-for-storage' };
  assert.equal((await f.request(`/api/staff/payloads/${deviceId}/connections`, 'POST', { ...input, integrationId: 'unknown' })).status, 400);
  assert.equal(verified, undefined);
  assert.equal((await f.request(`/api/staff/payloads/${deviceId}/connections`, 'POST', input)).status, 200);
  assert.equal(verified.requireComplete, true);
  const call = f.calls.find(item => item.name === 'bind_staff_payload_radio');
  assert.equal(call.args.p_integration_id, integration.id);
  assert.equal(call.args.p_ttn_device_id, 'network-device');
  assert.doesNotMatch(JSON.stringify(f.calls), /synthetic-ttn-key/);
});

test('full provisioning verification reads matching IS, NS, AS and JS registries', async () => {
  const ids = { device_id: 'network-device', dev_eui: devEui, join_eui: '0000000000000001', application_ids: { application_id: 'test-app' } };
  const input = { cluster: 'nam1', applicationId: 'test-app', deviceEui: devEui, apiKey: 'synthetic-ttn-key-not-for-storage', requireComplete: true };
  const urls = [];
  const fetcher = async (url, options) => {
    urls.push(url); assert.equal(options.method, undefined); assert.equal(options.redirect, 'error');
    if (url.includes('?field_mask=ids,join_server_address')) return Response.json({ end_devices: [{ ids, join_server_address: 'eu1.cloud.thethings.network' }] });
    return Response.json({ ids, supports_join: true, frequency_plan_id: 'US_902_928_FSB_2' });
  };
  assert.equal((await verifyTTNDevice(input, fetcher)).deviceId, ids.device_id);
  assert.equal(urls.length, 4);
  assert.match(urls[2], /^https:\/\/nam1.cloud.thethings.network\/api\/v3\/as\//);
  assert.match(urls[3], /^https:\/\/eu1.cloud.thethings.network\/api\/v3\/js\//);
  await assert.rejects(() => verifyTTNDevice(input, async (url, options) => url.includes('/as/') ? Response.json({ ids: { ...ids, dev_eui: '0000000000000001' } }) : fetcher(url, options)), /registries disagree/);
  await assert.rejects(() => verifyTTNDevice(input, async (url, options) => url.includes('?field_mask=ids,join_server_address') ? Response.json({ end_devices: [{ ids, join_server_address: 'evil.example' }] }) : fetcher(url, options)), /Join Server address/);
});
