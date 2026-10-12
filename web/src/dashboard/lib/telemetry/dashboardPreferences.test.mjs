import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultFleetFilters, readFleetFilters, saveFleetFilters, filterFleet } from './fleetFilters.ts';
import { readLayerVisibility } from './dashboardPreferences.ts';

const storage = (initial = {}) => {
    const values = new Map(Object.entries(initial));
    return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
};

test('planned balloons, sorting, search and ownership survive a new dashboard session', () => {
    const saved = storage();
    const filters = { ...defaultFleetFilters, planned: true, active: false, inactive: false, sort: 'oldest', query: 'Next launch', mine: true };
    saveFleetFilters(saved, filters);
    const restored = readFleetFilters(saved);
    assert.deepEqual(restored, filters);
    const balloon = { id: 'next', callsign: 'Next launch', status: 'planned', ownerId: 'pilot', lastContactT: null };
    assert.deepEqual(filterFleet([balloon], restored, 'pilot', Date.now()), [balloon]);
    saveFleetFilters(saved, defaultFleetFilters);
    assert.deepEqual(readFleetFilters(saved), defaultFleetFilters);
});

test('invalid and unavailable storage do not hide the fleet or change filter defaults', () => {
    for (const value of ['{', 'null', 'false', '[]']) assert.deepEqual(readFleetFilters(storage({ 'stratolink-dashboard-filters': value })), defaultFleetFilters);
    const saved = storage({ 'stratolink-dashboard-filters': JSON.stringify({ planned: true, inactive: 'false', sort: 'invalid', query: null }) });
    assert.deepEqual(readFleetFilters(saved), { ...defaultFleetFilters, planned: true });
    const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('full'); } };
    assert.deepEqual(readFleetFilters(blocked), defaultFleetFilters);
    assert.doesNotThrow(() => saveFleetFilters(blocked, defaultFleetFilters));
    assert.equal(readLayerVisibility(blocked, 'flight-paths', false), false);
});

test('one saved path preference overrides both legacy fleet and detail switches', () => {
    const saved = storage({ 'stratolink-dashboard-flight-tails': 'true', 'stratolink-dashboard-detail-paths': 'false' });
    const read = () => readLayerVisibility(saved, 'flight-paths', false, ['flight-tails', 'detail-paths']);
    assert.equal(read(), true);
    saved.setItem('stratolink-dashboard-flight-paths', 'false');
    assert.equal(read(), false);
    assert.equal(readLayerVisibility(storage({ 'stratolink-dashboard-detail-paths': 'true' }), 'flight-paths', false, ['flight-tails', 'detail-paths']), true);
});
