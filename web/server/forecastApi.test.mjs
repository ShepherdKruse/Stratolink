import assert from 'node:assert/strict';
import test from 'node:test';
import { createForecastApi } from './forecastApi.js';
import { readPrivateForecast } from './forecastStorage.js';

function response() {
  return { statusCode: 0, headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(body) { this.body = JSON.parse(body); } };
}
const request = (url = '/api/forecast?device=stratolink-3', method = 'GET') => ({ url, method });
const fixture = { generated_at: '2026-10-06T18:00:00Z', nominal_path: [[-122.40, 37.78], [-120, 40]], metadata: { secret: 'private' }, observed: { launch: { lat: 37.78, lon: -122.40 }, reconstructed_path: [] } };

test('forecast serves sanitized private stored data only for a connected public device', async () => {
  const handler = createForecastApi({ isPublicDevice: async () => true, readForecast: async () => fixture });
  const res = response(); await handler(request(), res);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body.nominal_path, [[-122.44, 37.76], [-120, 40]]);
  assert.equal(res.body.metadata, undefined);
  assert.equal(res.body.observed.launch, undefined);
  assert.equal(res.headers['Cache-Control'], 'no-store');
});

test('fleet path responses preserve privacy and omit detail geometry and metadata', async () => {
  const raw = { ...fixture, ensemble: [[[10, 20], [30, 40]]], ellipses: [{ e90: { polygon: [[10, 20], [30, 40], [10, 20]] } }] };
  const handler = createForecastApi({ isPublicDevice: async () => true, readForecast: async () => raw });
  const path = response(); await handler(request('/api/forecast?device=stratolink-3&view=path'), path);
  const full = response(); await handler(request(), full);
  assert.equal(path.statusCode, 200);
  assert.equal(path.headers['Cache-Control'], 'no-store');
  assert.deepEqual(path.body, { generated_at: raw.generated_at, nominal_path: full.body.nominal_path });
  assert.deepEqual(path.body.nominal_path, [[-122.44, 37.76], [-120, 40]]);
  assert.deepEqual(full.body.ensemble, raw.ensemble);
  assert.deepEqual(full.body.ellipses, raw.ellipses);
  assert.equal(raw.nominal_path[0][0], -122.40);
});

test('fleet path requests retain public-device gating and pending responses', async () => {
  const url = '/api/forecast?device=stratolink-3&view=path';
  const privateHandler = createForecastApi({ isPublicDevice: async () => false, readForecast: async () => { throw Error('must not read'); } });
  const hidden = response(); await privateHandler(request(url), hidden); assert.equal(hidden.statusCode, 404);
  const pendingHandler = createForecastApi({ isPublicDevice: async () => true, readForecast: async () => null });
  const pending = response(); await pendingHandler(request(url), pending);
  assert.equal(pending.statusCode, 202);
  assert.deepEqual(pending.body, { status: 'pending', device: 'stratolink-3' });
});

test('unsupported forecast views fail before registry or storage access', async () => {
  const handler = createForecastApi({ isPublicDevice: async () => { throw Error('must not read'); } });
  for (const view of ['', 'raw', 'metadata', 'PATH']) {
    const res = response(); await handler(request(`/api/forecast?device=stratolink-3&view=${view}`), res);
    assert.equal(res.statusCode, 400);
  }
});

test('unknown and unconnected devices never access forecast storage', async () => {
  const handler = createForecastApi({ isPublicDevice: async () => false, readForecast: async () => { throw new Error('must not run'); } });
  const res = response(); await handler(request(), res); assert.equal(res.statusCode, 404);
});

test('missing forecast is pending; storage failure does not masquerade as pending', async () => {
  for (const [readForecast, status] of [[async () => null, 202], [async () => { throw new Error('secret error detail'); }, 503]]) {
    const handler = createForecastApi({ isPublicDevice: async () => true, readForecast });
    const res = response(); await handler(request(), res); assert.equal(res.statusCode, status);
    assert.ok(!JSON.stringify(res.body).includes('secret'));
  }
});

test('forecast rejects malformed device IDs and non-GET methods before registry access', async () => {
  const handler = createForecastApi({ isPublicDevice: async () => { throw new Error('must not run'); } });
  for (const url of ['/api/forecast', '/api/forecast?device=../../secret', '/api/forecast?device=a%2Fb', `/api/forecast?device=${'a'.repeat(81)}`]) {
    const res = response(); await handler(request(url), res); assert.equal(res.statusCode, 400);
  }
  const res = response(); await handler(request(undefined, 'POST'), res); assert.equal(res.statusCode, 405);
});

test('private forecast reader authenticates Blob and distinguishes missing from failed reads', async () => {
  const getBlob = async (path, options) => {
    assert.equal(path, 'forecasts/stratolink-3.json');
    assert.deepEqual(options, { access: 'private', useCache: false, token: 'test-token' });
    return { statusCode: 200, stream: new Response(JSON.stringify(fixture)).body };
  };
  assert.deepEqual(await readPrivateForecast('stratolink-3', { getBlob, token: 'test-token' }), fixture);
  assert.equal(await readPrivateForecast('stratolink-3', { getBlob: async () => null, token: 'test-token' }), null);
  await assert.rejects(readPrivateForecast('stratolink-3', { getBlob: async () => { throw new Error('outage'); }, token: 'test-token' }));
  await assert.rejects(readPrivateForecast('stratolink-3', { getBlob, token: '' }));
});

test('private forecast reader bounds and validates stored content', async () => {
  for (const body of ['not json', '{}', ' '.repeat(8 * 1024 * 1024 + 1)]) {
    await assert.rejects(readPrivateForecast('stratolink-3', { token: 'test-token', getBlob: async () => ({ statusCode: 200, stream: new Response(body).body }) }));
  }
});
