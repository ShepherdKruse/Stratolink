import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitizeTelemetry, sanitizeDevice, sanitizeForecast, SAN_FRANCISCO } from './locationPrivacy.js';
import { buildQuery } from './dashboardApi.js';
test('city positions collapse to one approximate point without dropping packets or measurements', () => {
  const row = { time: '2026-01-01', lat: 37.775, lon: -122.415, temperature: 22, gateways: [{gateway_id:'private-name',lat:37.775,lon:-122.415,rssi:-90}] };
  const result=sanitizeTelemetry(row);
  assert.equal(result.lat, SAN_FRANCISCO.lat); assert.equal(result.lon, SAN_FRANCISCO.lon);
  assert.equal(result.location_approximate,true); assert.equal(result.temperature,22); assert.equal(result.time,row.time);
  assert.equal(result.gateways[0].gateway_id,'sf-receiver-1'); assert.equal(row.lat,37.775);
  assert.equal(sanitizeDevice({launch_lat:37.775,launch_lon:-122.415}).launch_lat,SAN_FRANCISCO.lat);
});
test('forecast geometries and hidden source metadata cannot reveal protected positions', () => {
 const raw={metadata:{private:'secret'},forecast_origin:{lat:37.775,lon:-122.415,time_utc:'today'},nominal_path:[[-122.415,37.775],[0,45]],observed:{launch:{name:'secret'},reconstructed_track:[{lat:37.775,lon:-122.415,time_utc:'today'}]},ensemble:[[[-122.415,37.775],[0,45]]],ellipses:[{e50:{polygon:[[-122.415,37.775],[0,45]]}}]};
 const safe=sanitizeForecast(raw); const text=JSON.stringify(safe);
 assert.ok(!text.includes('secret'));assert.ok(!text.includes('37.775'));assert.ok(!text.includes('-122.415')); assert.deepEqual(safe.nominal_path[1],[0,45]);
});
test('privacy endpoint rejects coordinate probing, arbitrary fields and nested relationships', () => {
 const base={resource:'telemetry',select:'lat',device_id:'eq.stratolink-2'};
 assert.ok(buildQuery(new URLSearchParams(base)).query.get('select').includes('lon'));
 for(const extra of [{lat:'gte.37.775'},{select:'*'},{select:'gateways(*)'},{order:'lat.asc'},{or:'(lat.gt.37)'},{resource:'secrets'}]) assert.throws(()=>buildQuery(new URLSearchParams({...base,...extra})));
});
