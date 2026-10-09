import assert from 'node:assert/strict';
import test from 'node:test';
import { positionAtTime, rowAtTime } from './fleetPlayback.ts';

const packet = (t, values = {}) => ({ t, lat: 10, lon: 20, alt: 1000, ...values });

test('row selection uses the last packet at or before the cursor without borrowing future data', () => {
    const rows = [packet(100), packet(200), packet(400)];
    assert.equal(rowAtTime([], null), null);
    assert.equal(rowAtTime(rows, 99), null);
    assert.equal(rowAtTime(rows, 100), rows[0]);
    assert.equal(rowAtTime(rows, 199), rows[0]);
    assert.equal(rowAtTime(rows, 200), rows[1]);
    assert.equal(rowAtTime(rows, 1000), rows[2]);
    assert.equal(rowAtTime(rows, null), rows[2]);
});

test('positions remain absent until the first complete GPS fix', () => {
    const noGps = [packet(100, { lat: null }), packet(200, { lon: null })];
    const rows = [...noGps, packet(300, { lat: 12, lon: 22 })];
    assert.equal(positionAtTime([], null), null);
    assert.equal(positionAtTime(noGps, null), null);
    assert.equal(positionAtTime(rows, 99), null);
    assert.equal(positionAtTime(rows, 250), null);
    assert.deepEqual(positionAtTime(rows, 300), { lat: 12, lon: 22, altitude_m: 1000 });
    assert.equal(rowAtTime(rows, 200), rows[1]);
});

test('replay interpolates positions and holds the last fix after a mission ends', () => {
    const rows = [packet(100), packet(200, { lat: 14, lon: 28, alt: 2000 })];
    assert.deepEqual(positionAtTime(rows, 150), { lat: 12, lon: 24, altitude_m: 1000 });
    const lastPosition = { lat: 14, lon: 28, altitude_m: 2000 };
    assert.deepEqual(positionAtTime(rows, 200), lastPosition);
    assert.deepEqual(positionAtTime(rows, 1000), lastPosition);
    assert.deepEqual(positionAtTime(rows, null), lastPosition);
});

test('an exact interior GPS fix uses that packet altitude as well as its coordinates', () => {
    const rows = [
        packet(100),
        packet(200, { lat: 14, lon: 28, alt: 2000 }),
        packet(300, { lat: 18, lon: 36, alt: 3000 }),
    ];
    assert.deepEqual(positionAtTime(rows, 200), { lat: 14, lon: 28, altitude_m: 2000 });
    assert.equal(positionAtTime(rows, 200).altitude_m, rowAtTime(rows, 200).alt);
});

test('longitude interpolation takes the short route across either side of the antimeridian', () => {
    for (const [start, end, quarter] of [[179, -179, 179.5], [-179, 179, -179.5]]) {
        const rows = [packet(100, { lon: start }), packet(200, { lon: end })];
        assert.equal(positionAtTime(rows, 125).lon, quarter);
        assert.equal(positionAtTime(rows, 150).lon, -180);
        assert.ok(Math.abs(positionAtTime(rows, 175).lon) > 179);
    }
});

test('one fleet cursor selects each mission independently across different launch dates', () => {
    const first = [packet(100), packet(200, { lat: 12, lon: 22 })];
    const second = [packet(300, { lat: 40, lon: 50 }), packet(400, { lat: 44, lon: 54 })];
    assert.deepEqual(positionAtTime(first, 150), { lat: 11, lon: 21, altitude_m: 1000 });
    assert.equal(positionAtTime(second, 150), null);
    assert.equal(rowAtTime(second, 150), null);
    assert.deepEqual(positionAtTime(first, 350), { lat: 12, lon: 22, altitude_m: 1000 });
    assert.equal(rowAtTime(first, 350), first[1]);
    assert.deepEqual(positionAtTime(second, 350), { lat: 42, lon: 52, altitude_m: 1000 });
    assert.equal(rowAtTime(second, 350), second[0]);
});

test('scrubbing never changes packet order, coordinates, or values', () => {
    const rows = Object.freeze([
        Object.freeze(packet(100, { lon: 179 })),
        Object.freeze(packet(150, { lat: null, lon: null })),
        Object.freeze(packet(200, { lon: -179 })),
    ]);
    const before = structuredClone(rows);
    for (const time of [null, 0, 100, 125, 150, 175, 200, 1000]) {
        rowAtTime(rows, time);
        positionAtTime(rows, time);
    }
    assert.deepEqual(rows, before);
});

test('fleet counts only recently transmitting, unfinished missions as active', async () => {
    const { fleetActivity } = await import('./fleetPlayback.ts');
    const now = 2_000_000;
    const devices = [
        { id: 'recent', status: 'flying' },
        { id: 'old', status: 'flying' },
        { id: 'landed', status: 'landed' },
        { id: 'empty', status: 'flying' },
    ];
    assert.deepEqual(fleetActivity(devices, {
        recent: [packet(now - 1000)], old: [packet(now - 900_000)], landed: [packet(now - 1000)],
    }, now), { active: 1, inactive: 3 });
    assert.deepEqual(fleetActivity(devices, {}, now), { active: 0, inactive: 4 });
});

test('homepage globe prioritizes active flights and falls back to recorded balloons', async () => {
    const { previewFleet } = await import('./fleetPlayback.ts');
    const devices = [{ id: 'active', status: 'flying' }, { id: 'past', status: 'landed' }, { id: 'new', status: 'idle' }];
    const rows = { active: [packet(1_999_000)], past: [packet(1000)] };
    assert.deepEqual(previewFleet(devices, rows, 2_000_000).map(d => d.id), ['active']);
    assert.deepEqual(previewFleet(devices, rows, 4_000_000).map(d => d.id), ['active', 'past']);
    assert.deepEqual(previewFleet(devices, {}, 4_000_000), []);
});

test('binary replay matches packet boundaries throughout a long flight and after refresh', () => {
    const rows = Array.from({ length: 20000 }, (_, i) => packet(i * 100, {
        lat: i % 5 === 0 ? null : 10 + i / 10000,
        lon: i % 5 === 0 ? null : 20 + i / 10000,
    }));
    for (const time of [0, 99, 100, 101, 999, 123456, 1500000, 1999999]) {
        assert.equal(rowAtTime(rows, time), rows[Math.min(rows.length - 1, Math.floor(time / 100))]);
        const fixes = rows.filter(row => row.lat !== null);
        const before = fixes.filter(row => row.t <= time).at(-1);
        const after = fixes.find(row => row.t >= time);
        const position = positionAtTime(rows, time);
        if (!before) assert.equal(position, null);
        else if (!after) assert.equal(position.lat, before.lat);
        else assert.ok(position.lat >= before.lat && position.lat <= after.lat);
    }
    const refreshed = [...rows, packet(2000000, { lat: 42 })];
    assert.equal(positionAtTime(refreshed, null).lat, 42);
    assert.notEqual(positionAtTime(rows, null).lat, 42);
});

test('duplicate timestamps keep the last packet while position interpolation retains its first matching fix', () => {
    const rows = [packet(100), packet(200, {lat: 11}), packet(200, {lat: 12}), packet(300, {lat: 13})];
    assert.equal(rowAtTime(rows, 200), rows[2]);
    assert.equal(positionAtTime(rows, 200).lat, 11);
    assert.equal(positionAtTime(rows, 250).lat, 12.5);
});

test('card altitude holds the last measured value without reading ahead across missing packets', async () => {
    const { altitudeAtTime } = await import('./fleetPlayback.ts');
    const rows = [packet(100, {alt: null}), packet(200, {presAlt: 500}), packet(300, {alt: null}), packet(400, {alt: 1200})];
    assert.equal(altitudeAtTime(rows, 100), null);
    assert.equal(altitudeAtTime(rows, 200), 500);
    assert.equal(altitudeAtTime(rows, 350), 500);
    assert.equal(altitudeAtTime(rows, 400), 1200);
});

test('planned launches and bench packets never appear in the homepage flight preview', async () => {
    const { previewFleet, fleetActivity } = await import('./fleetPlayback.ts');
    const plans = ['planned','storage','idle'].map(status => ({id:status,status}));
    const rows = Object.fromEntries(plans.map(device => [device.id,[packet(1_999_000)]]));
    assert.deepEqual(previewFleet(plans,rows,2_000_000),[]);
    assert.equal(fleetActivity(plans,rows,2_000_000).active,0);
});
