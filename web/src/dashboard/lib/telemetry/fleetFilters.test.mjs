import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultFleetFilters, filterFleet, isActiveBalloon, registeredStatus, registrationValues } from './fleetFilters.ts';
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
    assert.deepEqual(filter({active:false}),['draft','stratolink-2','stratolink-3']);
    assert.deepEqual(filter({active:false,inactive:false}),[]);
});
test('launch sorting puts undated registrations last and does not mutate input', () => {
    assert.deepEqual(filter({sort:'newest'}),['live','stratolink-3','stratolink-2','draft']);
    assert.deepEqual(filter({sort:'oldest'}),['stratolink-2','stratolink-3','live','draft']);
    assert.equal(devices[0].id,'stratolink-3');
});
test('search accepts display names and ownership filter requires an account', () => {
    assert.deepEqual(filter({query:'Stratolink 3'}),['stratolink-3']);
    assert.deepEqual(filter({mine:true},'owner-123'),['draft','live']);
    assert.deepEqual(filter({mine:true}),[]);
});
test('registered terminal status takes precedence over replay status', () => {
    assert.equal(registeredStatus('landed'),'Landed');
    assert.equal(registeredStatus('missing'),'Missing');
    assert.equal(registeredStatus('flying'),null);
});
test('registration normalizes EUI and rejects malformed identifiers', () => {
    assert.deepEqual(registrationValues('  Test 1  ','70:b3:d5:7e:d0:00:00:00'),{callsign:'Test 1',devEui:'70B3D57ED0000000'});
    assert.throws(()=>registrationValues('Test','not-an-eui'),/16 hexadecimal/);
    assert.throws(()=>registrationValues('A','70B3D57ED0000000'),/2 and 40/);
    assert.throws(()=>registrationValues('<Test>','70B3D57ED0000000'),/letters/);
    assert.throws(()=>registrationValues('-Test','70B3D57ED0000000'),/Start/);
    assert.throws(()=>registrationValues('Test','0000000000000000'),/all zeros/);
});
