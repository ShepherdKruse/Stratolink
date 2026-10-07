import assert from 'node:assert/strict';
import test from 'node:test';
import { flightTail, TAIL_WINDOW_MS } from './flightTail.ts';
const hour = 3_600_000;
const point = (h, lon = h) => ({ t: h * hour, lat: 30, lon });

test('tail includes only the last six hours and clips to an interpolated replay head', () => {
    const rows = Array.from({ length: 11 }, (_, i) => point(i));
    const tail = flightTail(rows, 8.5 * hour, 6 * hour);
    assert.equal(tail.points[0].t, 2.5 * hour);
    assert.equal(tail.points.at(-1).t, 8.5 * hour);
    assert.equal(tail.points.at(-1).lon, 8.5);
    assert.equal(tail.opacity, 1);
    assert.ok(tail.points.every(p => p.t <= 8.5 * hour));
    assert.equal(flightTail(rows, null, 6 * hour).points[0].t, 4 * hour);
});

test('held fleet markers retain their own last recorded tail even after another mission ends', () => {
    const points = [point(0), point(1), point(2)];
    assert.equal(flightTail(points, 500 * hour).opacity, 1);
    assert.deepEqual(flightTail(points, 500 * hour).points, flightTail(points, null).points);
    assert.deepEqual(flightTail(points, -hour).points, []);
    assert.deepEqual(flightTail([], null).points, []);
});

test('default tail includes movement before a twelve-hour repeated GPS fix', () => {
    const points = [point(0, 0), point(8, 2), point(20, 2)];
    const tail = flightTail(points, null);
    assert.equal(TAIL_WINDOW_MS, 24 * hour);
    assert.ok(new Set(tail.points.map(p => p.lon)).size > 1);
});

test('tails never bridge long telemetry gaps or borrow distant future fixes', () => {
    const tail = flightTail([point(0), point(1), point(20)], 18 * hour, 6 * hour);
    assert.deepEqual(tail.points, []);
    assert.deepEqual(flightTail([point(0), point(1), point(20), point(21)], null, 6 * hour).points, [point(20), point(21)]);
});

test('boundary interpolation takes the short route over the dateline without mutating fixes', () => {
    const points = Object.freeze([Object.freeze(point(0, 179)), Object.freeze(point(2, -179))]);
    const tail = flightTail(points, hour);
    assert.equal(tail.points.at(-1).lon, -180);
    assert.equal(points[0].lon, 179);
});
