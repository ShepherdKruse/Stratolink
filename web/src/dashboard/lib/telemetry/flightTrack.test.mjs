import assert from 'node:assert/strict';
import test from 'node:test';
import { flightTrack } from './flightTrack.ts';
test('GPS spikes do not become flight paths while valid travel is retained', () => {
  const rows = [{ t: 0, lat: 37, lon: -122 }, { t: 60000, lat: 25, lon: -122 }, { t: 120000, lat: 37.01, lon: -122 }, { t: 180000, lat: -208, lon: 0 }];
  assert.deepEqual(flightTrack(rows), [rows[0], rows[2]]);
  assert.equal(rows.length, 4);
});
