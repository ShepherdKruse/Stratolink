import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeRegisteredBalloons } from '../community/types.ts';
import { defaultFleetFilters, filterFleet } from './fleetFilters.ts';

const user = 'owner-123';
const record = { id:'balloon-123', callsign:'Test', status:'landed', devEui:'70B3D57ED0000000', ownerId:user, ownerGithub:'pilot', registeredAt:'2026-10-06T00:00:00Z', launchedAt:10, connections:[], connectionStatus:'pending' };
const fix = { lat:30, lon:-80, alt:10000, t:300 };

test('own account metadata overlays one registry entry without losing telemetry', () => {
    const registry = [{ id:'balloon-123', callsign:'Old name', status:'flying', launchedAt:10, launchLat:30, launchLon:-80, lastContactT:300, latestFix:fix, official:false }];
    const merged = mergeRegisteredBalloons(registry, [record]);
    assert.equal(merged.length, 1);
    assert.equal(merged[0].status, 'landed');
    assert.equal(merged[0].callsign, 'Test');
    assert.equal(merged[0].ownerId, user);
    assert.equal(merged[0].lastContactT, 300);
    assert.equal(merged[0].latestFix, fix);
    assert.equal(merged[0].official, false);
    assert.equal(registry[0].status, 'flying');
});

test('pending ownership records do not invent positions or official status', () => {
    const [merged] = mergeRegisteredBalloons([], [record]);
    assert.equal(merged.latestFix, null);
    assert.equal(merged.lastContactT, null);
    assert.equal(merged.launchLat, null);
    assert.equal(merged.launchLon, null);
    assert.notEqual(merged.official, true);
});

test('mine filters require the immutable account ID, not a copied or changed GitHub name', () => {
    const owned = mergeRegisteredBalloons([], [record]);
    const spoofed = { ...owned[0], id:'another-balloon', ownerId:'another-owner', ownerGithub:'pilot' };
    const filters = { ...defaultFleetFilters, mine:true };
    assert.deepEqual(filterFleet([...owned, spoofed], filters, user, 1000).map(device => device.id), ['balloon-123']);
    assert.deepEqual(filterFleet(owned, filters, 'pilot', 1000), []);
    assert.deepEqual(filterFleet([{ ...owned[0], ownerGithub:'renamed-pilot' }], filters, user, 1000).map(device => device.id), ['balloon-123']);
});

test('OAuth returns only to a validated balloon on the fixed dashboard route', async () => {
    const { dashboardReturnDevice, storedReturnDevice } = await import('../community/returnDevice.ts');
    assert.equal(dashboardReturnDevice('https://stratolink.org/dashboard?device=stratolink-3&next=https://evil.example'), 'stratolink-3');
    assert.equal(dashboardReturnDevice('https://stratolink.org/?device=stratolink-3'), null);
    assert.equal(dashboardReturnDevice('https://stratolink.org/dashboard?device=https://evil.example'), null);
    assert.equal(storedReturnDevice(JSON.stringify({ device:'stratolink-3', createdAt:1000 }), 2000), 'stratolink-3');
    for (const value of [null, '{', 'null', JSON.stringify({ device:'//evil.example', createdAt:1000 }), JSON.stringify({ device:'stratolink-3', createdAt:3000 }), JSON.stringify({ device:'stratolink-3', createdAt:0 })]) {
        assert.equal(storedReturnDevice(value, 1_000_000), null);
    }
});
test('shared official balloons appear in the current account filter without changing their primary owner', () => {
    const shared = { ...record, ownerId:null, ownerGithub:null, official:true, sharedWith:['Twarner491','clkruse','ShepherdKruse'] };
    const merged = mergeRegisteredBalloons([], [shared], user);
    const filters = { ...defaultFleetFilters,mine:true };
    assert.equal(merged[0].ownerId,undefined);
    assert.equal(merged[0].official,true);
    assert.equal(filterFleet(merged,filters,user,1000).length,1);
    assert.equal(filterFleet(merged,filters,'another-account',1000).length,0);
    assert.equal(filterFleet(merged,filters,null,1000).length,0);
    assert.equal(mergeRegisteredBalloons([],[],undefined).length,0);
});
