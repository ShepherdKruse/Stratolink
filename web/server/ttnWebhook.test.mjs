import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createTTNWebhook, extractGateways } from './ttnWebhook.ts';
import productionEntry from '../api/ttn-webhook.ts';

const secret = 'unit-test-integration-secret-with-32-characters';
const binding = {
  canonical_device_id: 'community-balloon',
  integration_id: '10000000-0000-4000-8000-000000000001',
  radio_identity_id: '20000000-0000-4000-8000-000000000002',
  identity_mismatch: false,
};
const frame = Buffer.alloc(40);
frame.writeUInt16BE(4660, 18);
frame[35] = 7;
frame.writeUInt16BE(0x91ff, 36);
const fixture = () => ({
  end_device_ids: { device_id: 'a-different-callsign-eu', dev_addr: '260cacd0', dev_eui: '001122aabbcc4455', application_ids: { application_id: 'flight-testing' } },
  received_at: '2026-10-05T19:00:00.123456789Z',
  uplink_message: { f_port: 1, f_cnt: 7, frm_payload: frame.toString('base64'),
    decoded_payload: { telemetry_version: 2, gps_fix_age_min: 37375 },
    rx_metadata: [
      { gateway_ids: { eui: 'weak-gateway' }, channel_rssi: -105, snr: -4 },
      { gateway_ids: { gateway_id: 'near-gateway' }, rssi: -87, snr: 5.5, received_at: '2026-10-05T19:00:00.1Z', location: { latitude: 30, longitude: -100, altitude: 10 } },
    ],
    settings: { frequency: '903900000', data_rate: { lora: { spreading_factor: 7, bandwidth: 125000 } } },
  },
});
const request = (payload = fixture(), headers = {}) => new Request('https://stratolink.org/api/ttn-webhook', {
  method: 'POST', headers: { authorization: `Bearer ${secret}`, 'content-type': 'application/json', ...headers }, body: JSON.stringify(payload),
});
function harness(overrides = {}) {
  const lookups = [], inserts = [], received = [];
  const handler = createTTNWebhook({
    async resolveIdentity(input) { lookups.push(input); return binding; },
    async insert(table, row) { inserts.push({ table, row }); return { error: null }; },
    async markReceived(id, time) { received.push({ id, time }); return { error: null }; },
    ...overrides,
  });
  return { handler, lookups, inserts, received };
}

test('production entry uses the native Request handler without a Node body parser', async () => {
  assert.equal(typeof productionEntry.fetch, 'function');
  const result = await productionEntry.fetch(new Request('https://stratolink.org/api/ttn-webhook', { method: 'POST' }));
  assert.equal(result.status, 401);
});

test('verified integration routes all regional names to canonical balloon without suffix guessing', async () => {
  const h = harness();
  const input = fixture();
  assert.equal((await h.handler(request(input))).status, 200);
  assert.deepEqual(h.lookups, [{
    p_token_hash: createHash('sha256').update(secret).digest('hex'), p_application_id: 'flight-testing',
    p_ttn_device_id: 'a-different-callsign-eu', p_dev_eui: '001122AABBCC4455',
  }]);
  const { table, row } = h.inserts[0];
  assert.equal(table, 'telemetry');
  assert.equal(row.device_id, binding.canonical_device_id);
  assert.equal(row.integration_id, binding.integration_id);
  assert.equal(row.radio_identity_id, binding.radio_identity_id);
  assert.equal(row.ttn_device_id, input.end_device_ids.device_id);
  assert.equal(row.ttn_received_at, input.received_at);
  assert.equal(row.dev_addr, '260CACD0');
  assert.equal(row.telemetry_version, 3);
  assert.equal(row.server_proof_count_mod8, 1);
  assert.equal(row.gps_fix_age_min, null);
  assert.equal(row.frm_payload, input.uplink_message.frm_payload);
  assert.deepEqual(row.rx_metadata, input.uplink_message.rx_metadata);
  assert.equal(row.gateways[0].gateway_id, 'near-gateway');
  assert.equal(row.gateways[1].rssi, -105);
  assert.deepEqual(h.received, [{ id: binding.radio_identity_id, time: input.received_at }]);
});

test('unverified, revoked or mismatched bindings fail closed for every uplink port', async () => {
  for (const fPort of [1, 11, 12]) {
    const h = harness({ async resolveIdentity() { return null; } });
    const input = fixture(); input.uplink_message.f_port = fPort;
    const result = await h.handler(request(input));
    assert.equal(result.status, 401);
    assert.equal(h.inserts.length, 0);
    assert.equal(h.received.length, 0);
  }
  const h = harness({ async resolveIdentity() { throw new Error('secret DB error'); } });
  const result = await h.handler(request());
  assert.equal(result.status, 503);
  assert.ok(!(await result.text()).includes('secret'));
});

test('authenticated application webhooks ignore unrelated devices but reject partial identity matches', async () => {
  const ignored = harness({ async resolveIdentity() {
    return { ...binding, canonical_device_id: null, radio_identity_id: null };
  } });
  const input = fixture(); input.uplink_message.f_port = 42;
  const response = await ignored.handler(request(input));
  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), { ignored: true });
  assert.equal(ignored.inserts.length, 0);
  assert.equal(ignored.received.length, 0);
  const mismatched = harness({ async resolveIdentity() {
    return { ...binding, canonical_device_id: null, radio_identity_id: null, identity_mismatch: true };
  } });
  assert.equal((await mismatched.handler(request())).status, 401);
  assert.equal(mismatched.inserts.length, 0);
  const boundUnsupported = harness();
  assert.equal((await boundUnsupported.handler(request(input))).status, 400);
  assert.equal(boundUnsupported.inserts.length, 0);
});

test('missing token, invented network identity, malformed JSON and oversize bodies never reach the database', async () => {
  const h = harness();
  assert.equal((await h.handler(request(fixture(), { authorization: '' }))).status, 401);
  assert.equal((await h.handler(request(fixture(), { authorization: 'Bearer short' }))).status, 401);
  assert.equal((await h.handler(request(fixture(), { 'content-type': 'text/plain' }))).status, 415);
  assert.equal((await h.handler(new Request('https://stratolink.org/api/ttn-webhook'))).status, 405);
  for (const mutate of [
    p => delete p.end_device_ids.dev_eui,
    p => delete p.end_device_ids.application_ids,
    p => { p.end_device_ids.dev_eui = 'bad'; },
    p => { p.end_device_ids.device_id = 'other/device'; },
    p => { p.uplink_message.rx_metadata = [{} , null]; },
    p => { p.uplink_message.f_cnt = -1; },
    p => { p.uplink_message.frm_payload += '!'; },
  ]) {
    const input = fixture(); mutate(input);
    assert.equal((await h.handler(request(input))).status, 400);
  }
  assert.equal((await h.handler(request({ padding: 'a'.repeat(256 * 1024) }))).status, 413);
  assert.equal((await h.handler(request(fixture(), { 'content-length': String(300 * 1024) }))).status, 413);
  assert.equal(h.lookups.length, 0);
});

test('only exact scoped duplicate indexes acknowledge retries, and connection confirmation is retried', async () => {
  const h = harness({ async insert() { return { error: { code: '23505', message: 'duplicate key violates "telemetry_ttn_scoped_delivery"' } }; } });
  const result = await h.handler(request());
  assert.equal(result.status, 200);
  assert.equal((await result.json()).duplicate, true);
  assert.equal(h.received.length, 1);
  const wrong = harness({ async insert() { return { error: { code: '23505', message: 'duplicate key violates "other_unique"' } }; } });
  assert.equal((await wrong.handler(request())).status, 503);
  assert.equal(wrong.received.length, 0);
  const markFailed = harness({ async markReceived() { return { error: new Error('disconnected') }; } });
  assert.equal((await markFailed.handler(request())).status, 503);
});

test('CTT and authenticated B2B wire envelopes retain their typed contract and scoped identity', async () => {
  const ctt = Buffer.alloc(17);
  ctt[0] = 0x43; ctt[1] = 0x54; ctt[2] = 2;
  ctt.writeUInt32BE(1234, 4); ctt.writeInt16BE(-87, 12); ctt[14] = 1; ctt.writeUInt16BE(3, 15);
  const input = fixture(); input.uplink_message.f_port = 11; input.uplink_message.frm_payload = ctt.toString('base64');
  const h = harness();
  assert.equal((await h.handler(request(input))).status, 200);
  assert.equal(h.inserts[0].table, 'wildlife_detections');
  assert.equal(h.inserts[0].row.device_id, binding.canonical_device_id);
  assert.equal(h.inserts[0].row.detected_at, '2026-10-05T18:57:00.123Z');
  assert.equal(h.inserts[0].row.listen_window, null);
  const b2b = Buffer.from([0x53, 0x42, 3, 0, 1, 7, 1, 2, 11, 0, 2, 3, ...Array(8).fill(0x11)]);
  input.uplink_message.f_port = 12; input.uplink_message.frm_payload = b2b.toString('base64');
  assert.equal((await h.handler(request(input))).status, 200);
  assert.equal(h.inserts[1].table, 'b2b_packets');
  assert.equal(h.inserts[1].row.gateway_balloon_id, binding.canonical_device_id);
  assert.equal(h.inserts[1].row.device_id, undefined);
  assert.equal(h.inserts[1].row.raw_frame_base64, b2b.toString('base64'));
  assert.equal(h.inserts[1].row.command_seq, 3);
});

test('receiver normalization never converts missing coordinates into a plausible location', () => {
  assert.deepEqual(extractGateways([{ gateway_ids: { gateway_id: 'receiver' }, location: { latitude: 30 }, rssi: 'bad' }]), [
    { gateway_id: 'receiver', rssi: null, snr: null, lat: null, lon: null, alt: null },
  ]);
});
