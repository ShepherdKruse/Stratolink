import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultFleetFilters, filterFleet, isActiveBalloon, registeredStatus } from './fleetFilters.ts';
const now = 1_000_000;
const devices = [
    {id:'stratolink-3', status:'landed', lastContactT:now, launchedAt:300},
    {id:'stratolink-2', status:'missing', lastContactT:100, launchedAt:200},
    {id:'draft', callsign:'Alpha', ownerGithub:'pilot', ownerId:'owner-123', status:'planned', lastContactT:null, launchedAt:null},
    {id:'live', callsign:'Zenith', ownerGithub:'pilot', ownerId:'owner-123', status:'flying', lastContactT:now-100, launchedAt:400},
];
const filter = (changes, owner=null) => filterFleet(devices, {...defaultFleetFilters,...changes}, owner, now).map(d=>d.id);
test('active filters use freshness and preserve terminal states', () => {
    assert.equal(isActiveBalloon(devices[0],now),false);
    assert.deepEqual(filter({inactive:false}),['live']);
    assert.deepEqual(filter({active:false}),['stratolink-2','stratolink-3']);
    assert.deepEqual(filter({active:false,inactive:false}),[]);
});
test('launch sorting puts undated registrations last and does not mutate input', () => {
    assert.deepEqual(filter({sort:'newest'}),['live','stratolink-3','stratolink-2']);
    assert.deepEqual(filter({sort:'oldest'}),['stratolink-2','stratolink-3','live']);
    assert.equal(devices[0].id,'stratolink-3');
});
test('search accepts display names and ownership filter requires an account', () => {
    assert.deepEqual(filter({query:'Stratolink 3'}),['stratolink-3']);
    assert.deepEqual(filter({mine:true},'owner-123'),['live']);
    assert.deepEqual(filter({mine:true}),[]);
});
test('registered terminal status takes precedence over replay status', () => {
    assert.equal(registeredStatus('landed'),'Landed');
    assert.equal(registeredStatus('missing'),'Missing');
    assert.equal(registeredStatus('flying'),null);
});
test('planned launches have their own opt-in filter, including owned launches', () => {
    assert.deepEqual(filter({planned:true,active:false,inactive:false}),['draft']);
    assert.deepEqual(filter({planned:true,mine:true},'owner-123'),['draft','live']);
    assert.deepEqual(filter({query:'Alpha'}),[]);
    assert.deepEqual(filter({query:'Alpha',planned:true}),['draft']);
    assert.deepEqual(filter({sort:'newest',planned:true}),['live','stratolink-3','stratolink-2','draft']);
});
