import assert from 'node:assert/strict';
import test from 'node:test';
import { fleetTailSources, unwrapLngs } from './flightTail.ts';
const hour = 3_600_000;
const path = (deviceId, color, offset = 0) => ({ deviceId, color, points: [
    { t: offset, lat: 30, lon: 179 },
    { t: offset + hour, lat: 31, lon: -179 },
] });

test('a thousand fleet tails use four palette sources without joining separate balloons', () => {
    const colors = ['#a23a2d', '#476f83', '#7a7650', '#806682'];
    const paths = Array.from({ length: 1000 }, (_, i) => path(`balloon-${i}`, colors[i % 4]));
    const sources = fleetTailSources(paths, null);
    assert.equal(sources.length, 4);
    const features = sources.flatMap(source => source.data.features);
    assert.equal(features.length, 1000);
    assert.equal(new Set(features.map(feature => feature.id)).size, 1000);
    for (const source of sources) for (const feature of source.data.features) {
        assert.equal(paths[Number(feature.id.slice(8))].color, source.color);
        assert.equal(feature.geometry.type, 'LineString');
        assert.deepEqual(feature.geometry.coordinates, [[179, 30], [181, 31]]);
        assert.equal(feature.properties.opacity, 0.85);
    }
});

test('replay keeps each tail endpoint and opacity and omits flights that have not started', () => {
    const sources = fleetTailSources([path('first', '#123'), path('later', '#123', 2 * hour)], hour / 2);
    assert.equal(sources.length, 1);
    assert.equal(sources[0].data.features.length, 1);
    assert.deepEqual(sources[0].data.features[0].geometry.coordinates, [[179, 30], [180, 30.5]]);
    assert.equal(sources[0].data.features[0].properties.opacity, 0.85);
    assert.deepEqual(fleetTailSources([path('first', '#123')], -1), []);
    assert.deepEqual(fleetTailSources([], null), []);
});

test('unwrapping retains short arcs and does not change the source coordinates', () => {
    const original = [[179, 1], [-179, 2], [178, 3], [-178, 4]];
    assert.deepEqual(unwrapLngs(original), [[179, 1], [181, 2], [178, 3], [182, 4]]);
    assert.deepEqual(original, [[179, 1], [-179, 2], [178, 3], [-178, 4]]);
    assert.deepEqual(unwrapLngs([]), []);
});

test('a stale tail keeps its own opacity when sharing a color with a fresh flight', () => {
    const stale = path('stale', '#123');
    stale.points.push({ t: 48 * hour, lat: 35, lon: -170 });
    const fresh = path('fresh', '#123', 5 * hour);
    const features = fleetTailSources([stale, fresh], 6 * hour)[0].data.features;
    assert.equal(features[0].properties.opacity, (1 - 5 / 24) * 0.85);
    assert.equal(features[1].properties.opacity, 0.85);
});
