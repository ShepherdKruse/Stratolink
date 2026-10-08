import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldPollTelemetry, withLatestTelemetry } from './fleetSummary.ts';

test('fleet summaries reuse the last real fix while contact follows newer sensor packets', () => {
    const device = { id: 'balloon', lastContactT: null, latestFix: null };
    const history = [
        { t: 100, lat: 37.76, lon: -122.44, alt: 20 },
        { t: 200, lat: null, lon: null, alt: 25 },
    ];
    assert.deepEqual(withLatestTelemetry(device, history), {
        ...device, lastContactT: 200, latestFix: { lat: 37.76, lon: -122.44, alt: 20, t: 100 },
    });
    assert.equal(device.latestFix, null);
    assert.equal(history[1].lat, null);
    assert.equal(withLatestTelemetry(device, []), device);
    assert.equal(withLatestTelemetry(device, undefined), device);
});

test('finished flights stop polling but missing balloons can still report again', () => {
    for (const status of ['landed', 'recovered', 'retired', 'planned']) assert.equal(shouldPollTelemetry(status), false);
    for (const status of ['flying', 'missing', 'lost', 'idle']) assert.equal(shouldPollTelemetry(status), true);
});


test('summary identity survives unrelated history batches and updates with metadata or packets', () => {
    const device = { id: 'balloon', status: 'flying', lastContactT: null, latestFix: null };
    const history = [{ t: 100, lat: 37, lon: -122, alt: 20 }];
    const first = withLatestTelemetry(device, history);
    assert.equal(withLatestTelemetry(device, history), first);
    const next = withLatestTelemetry(device, [...history, { t: 200, lat: null, lon: null, alt: 25 }]);
    assert.notEqual(next, first);
    assert.equal(next.lastContactT, 200);
    assert.deepEqual(next.latestFix, first.latestFix);
    const landed = withLatestTelemetry({ ...device, status: 'landed' }, history);
    assert.notEqual(landed, first);
    assert.equal(landed.status, 'landed');
});
