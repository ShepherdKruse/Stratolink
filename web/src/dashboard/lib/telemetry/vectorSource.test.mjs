import assert from 'node:assert/strict';
import test from 'node:test';
import { ensureVectorSource } from '../../components/maps/vectorSource.ts';

test('terrain and bathymetry reuse the stock composite tileset without new sources', () => {
    const sources = { composite: { type: 'vector', url: 'mapbox://mapbox.mapbox-streets-v8,mapbox.mapbox-terrain-v2,mapbox.mapbox-bathymetry-v2' } };
    const map = { getStyle: () => ({ sources }), getSource: id => sources[id], addSource: () => assert.fail('duplicate source') };
    assert.equal(ensureVectorSource(map, 'terrain', 'mapbox.mapbox-terrain-v2'), 'composite');
    assert.equal(ensureVectorSource(map, 'depth', 'mapbox.mapbox-bathymetry-v2'), 'composite');
});

test('a basemap without the tileset gets one fallback source', () => {
    const sources = { base: { type: 'vector', url: 'mapbox://mapbox.mapbox-streets-v8' } };
    let additions = 0;
    const map = { getStyle: () => ({ sources }), getSource: id => sources[id], addSource(id, source) { additions++; sources[id] = source; } };
    assert.equal(ensureVectorSource(map, 'terrain', 'mapbox.mapbox-terrain-v2'), 'terrain');
    assert.equal(ensureVectorSource(map, 'terrain', 'mapbox.mapbox-terrain-v2'), 'terrain');
    assert.equal(additions, 1);
});

test('matching is exact and does not reuse raster or unrelated vector sources', () => {
    const sources = {
        raster: { type: 'raster', url: 'mapbox://mapbox.mapbox-terrain-v2' },
        other: { type: 'vector', url: 'mapbox://mapbox.mapbox-terrain-v20' },
    };
    const map = { getStyle: () => ({ sources }), getSource: id => sources[id], addSource(id, source) { sources[id] = source; } };
    assert.equal(ensureVectorSource(map, 'terrain', 'mapbox.mapbox-terrain-v2'), 'terrain');
    assert.equal(sources.terrain.type, 'vector');
});
