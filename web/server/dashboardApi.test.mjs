import test from 'node:test';
import assert from 'node:assert/strict';
import { buildQuery, dashboardApi } from './dashboardApi.js';
import { SAN_FRANCISCO } from './locationPrivacy.js';

function responseRecorder() {
  return { statusCode: 0, headers: {}, setHeader(name, value) { this.headers[name] = value; }, end(value) { this.value = JSON.parse(value); } };
}
test('public queries cannot expose raw packet evidence, ownership IDs or pending registrations', () => {
  for (const select of ['owner_id', 'claim_code', 'launch_token_hash']) assert.throws(() => buildQuery(new URLSearchParams({ resource: 'devices', select })));
  for (const select of ['frm_payload', 'rx_metadata', 'session_key_id', 'integration_id']) assert.throws(() => buildQuery(new URLSearchParams({ resource: 'telemetry', select })));
  assert.throws(() => buildQuery(new URLSearchParams({ resource: 'devices', select: 'device_id', connection_status: 'eq.pending' })));
  const devices = buildQuery(new URLSearchParams({ resource: 'devices', select: 'device_id,owner_github,official' }));
  assert.equal(devices.query.get('connection_status'), 'eq.connected');
  const health = buildQuery(new URLSearchParams({ resource: 'telemetry', select: 'telemetry_version,power_tier,server_proof_count_mod8' }));
  assert.ok(health.query.get('select').includes('gps_fix_age_min'));
});

test('public telemetry uses the connected-only database view and sanitizes before selecting fields', async () => {
  const savedFetch = globalThis.fetch;
  const previous = { url: process.env.SUPABASE_URL, key: process.env.SUPABASE_SERVER_KEY };
  const key = `test.${Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url')}.not-a-real-key`;
  process.env.SUPABASE_URL = 'https://example.supabase.co'; process.env.SUPABASE_SERVER_KEY = key;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url: new URL(url), options });
    return Response.json([{ id: 'packet', lat: 37.775, lon: -122.415, telemetry_version: 3, frm_payload: 'private', owner_id: 'private' }]);
  };
  try {
    const response = responseRecorder();
    await dashboardApi({ method: 'GET', url: '/api/telemetry?resource=telemetry&select=id,lat,telemetry_version' }, response);
    assert.equal(response.statusCode, 200);
    assert.equal(calls[0].url.pathname, '/rest/v1/community_telemetry');
    assert.equal(calls[0].options.headers.apikey, key);
    assert.deepEqual(response.value, [{ id: 'packet', lat: SAN_FRANCISCO.lat, telemetry_version: 3, location_approximate: true }]);
    assert.ok(!JSON.stringify(response.value).includes('private'));
    const devices = responseRecorder();
    await dashboardApi({ method: 'GET', url: '/api/telemetry?resource=devices&select=device_id' }, devices);
    assert.equal(calls[1].url.searchParams.get('connection_status'), 'eq.connected');
  } finally {
    globalThis.fetch = savedFetch;
    if (previous.url === undefined) delete process.env.SUPABASE_URL; else process.env.SUPABASE_URL = previous.url;
    if (previous.key === undefined) delete process.env.SUPABASE_SERVER_KEY; else process.env.SUPABASE_SERVER_KEY = previous.key;
  }
});
