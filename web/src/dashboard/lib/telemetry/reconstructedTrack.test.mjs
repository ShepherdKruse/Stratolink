import assert from 'node:assert/strict';
import test from 'node:test';
import { cleanReconstructedTrack, reconstructedFlightTrack } from './reconstructedTrack.ts';
import { flightTail, fleetTailSources } from './flightTail.ts';
const hour = 3_600_000;
const point = (h, lon, lat = 30) => ({ t: h * hour, lon, lat });

test('historical winds give repeated GPS reports a visible tail months after the flight', () => {
    const fixes = [point(0, 10), point(12, 10), point(24, 10)];
    const wind = Array.from({ length: 25 }, (_, h) => point(h, 10 + Math.sin(Math.PI * h / 12), 30 + Math.sin(Math.PI * h / 12)));
    const track = reconstructedFlightTrack(fixes, wind);
    const sources = fleetTailSources([{ deviceId: 'recorded', color: '#123', points: track }], 120 * 24 * hour);
    assert.equal(sources.length, 1);
    const line = sources[0].data.features[0];
    assert.ok(new Set(line.geometry.coordinates.map(JSON.stringify)).size > 10);
    assert.deepEqual(line.geometry.coordinates.at(-1), [10, 30]);
    assert.equal(line.properties.opacity, 0.85);
    assert.equal(flightTail(track, 5.5 * hour).points.at(-1).t, 5.5 * hour);
});

test('wind history cannot extend beyond recorded flight bounds or override measured fixes', () => {
    const fixes = [point(10, 10), point(12, 12), point(14, 14)];
    const wind = [point(0, 0), point(10, 11), point(11, 13), point(12, 13), point(15, 15)];
    assert.deepEqual(reconstructedFlightTrack(fixes, wind), [fixes[0], wind[2], fixes[1], fixes[2]]);
    assert.deepEqual(reconstructedFlightTrack(fixes, []), fixes);
    assert.deepEqual(reconstructedFlightTrack([fixes[0]], wind), [fixes[0]]);
});

test('reconstruction parsing rejects corrupt coordinates and normalizes dateline crossings', () => {
    const rows = [
        { time_utc: new Date(hour).toISOString(), lat: 20, lon: 181 },
        { time_utc: new Date(0).toISOString(), lat: 20, lon: 179 },
        { time_utc: 'bad', lat: 20, lon: 10 },
        { time_utc: new Date(0).toISOString(), lat: 100, lon: 10 }, null,
    ];
    const track = cleanReconstructedTrack(rows);
    assert.deepEqual(track, [point(0, 179, 20), point(1, -179, 20)]);
    assert.equal(flightTail(track, hour / 2).points.at(-1).lon, -180);
    assert.deepEqual(cleanReconstructedTrack(null), []);
});
