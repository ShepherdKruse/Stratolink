import assert from 'node:assert/strict';

export function checkRegistrationPlanning({sql,service,denied,literal}) {
 const owner='40000000-0000-4000-8000-000000000001';
 const outsider='40000000-0000-4000-8000-000000000002';
 sql(`INSERT INTO auth.users(id) VALUES ('${owner}'),('${outsider}');`);
 const radios={northAmerica:'1122334455667788',europe:'2233445566778899',asia:'33445566778899AA',australia:'1122334455667788'};
 const args=`'${owner}','review-user','Launch review','2027-02-15',${literal(JSON.stringify(radios))}::jsonb,true`;
 for(const role of ['anon','authenticated']){
  denied(`SET ROLE ${role}; SELECT public.register_planned_balloon(${args});`);
  denied(`SET ROLE ${role}; SELECT public.update_balloon_settings('${owner}','stratolink-3','Forged',NULL,'{}',true);`);
  denied(`SET ROLE ${role}; SELECT regional_euis,share_research_data FROM community_private.balloon_registration;`);
 }
 const legacy=JSON.parse(service(`SELECT community_private.balloon_json('stratolink-3')`));
 assert.equal(legacy.shareResearchData,false,'existing owners are not silently opted in');
 const created=JSON.parse(service(`SELECT public.register_planned_balloon(${args});`));
 assert.equal(created.status,'planned');
 assert.equal(created.connectionStatus,'pending');
 assert.equal(created.plannedLaunchDate,'2027-02-15');
 assert.equal(created.shareResearchData,true);
 assert.deepEqual(created.regionalEuis,radios);
 assert.deepEqual(created.connections,[]);
 assert.equal(service(`SELECT count(*) FROM community_private.radio_identities WHERE device_id='${created.id}'`),'0');
 assert.equal(service(`SELECT count(*) FROM public.community_telemetry WHERE device_id='${created.id}'`),'0');
 const consent=service(`SELECT research_choice_at FROM community_private.balloon_registration WHERE device_id='${created.id}'`);
 assert.ok(consent);
 assert.equal(service(`SELECT public.update_balloon_settings('${outsider}','${created.id}','Hijacked',NULL,'{}',false) IS NULL`),'t');
 assert.equal(JSON.parse(service(`SELECT community_private.balloon_json('${created.id}')`)).shareResearchData,true);
 const changed=JSON.parse(service(`SELECT public.update_balloon_settings('${owner}','${created.id}','New callsign',NULL,'{}',false)`));
 assert.equal(changed.callsign,'New callsign');
 assert.equal(changed.plannedLaunchDate,null);
 assert.equal(changed.shareResearchData,false);
 assert.deepEqual(changed.regionalEuis,{});
 assert.equal(changed.devEui,created.devEui,'settings do not replace verified or primary identities');
 assert.notEqual(service(`SELECT research_choice_at FROM community_private.balloon_registration WHERE device_id='${created.id}'`),consent);
 for(const invalid of ["'[]'","'null'","'{\"nam1\":\"1122334455667788\"}'","'{\"asia\":123}'","'{\"asia\":\"0000000000000000\"}'"]){
  denied(`SET ROLE service_role; SELECT public.update_balloon_settings('${owner}','${created.id}','Bad',NULL,${invalid},false);`,/Invalid balloon settings/);
 }
 const before=service(`SELECT count(*) FROM public.devices`);
 denied(`SET ROLE service_role; SELECT public.register_planned_balloon('${owner}','review-user','Invalid date','2200-01-01','{"europe":"AABBCCDDEEFF8899"}',true);`,/check constraint/);
 assert.equal(service('SELECT count(*) FROM public.devices'),before,'registration and settings roll back together');
 // The latest team migration must still share registrations and settings.
 service(`SELECT public.sync_official_team_member('${owner}','48384497')`);
 service(`SELECT public.sync_official_team_member('${outsider}','13071901')`);
 const official=JSON.parse(service(`SELECT public.register_planned_balloon('${owner}','Twarner491','Official plan',NULL,'{"europe":"AABBCCDDEEFF8899"}',true)`));
 assert.equal(official.official,true);
 assert.equal(official.sharedWith.length,3);
 const coOwned=JSON.parse(service(`SELECT public.update_balloon_settings('${outsider}','${official.id}','Team plan','2027-03-01','{"europe":"AABBCCDDEEFF8899"}',false)`));
 assert.equal(coOwned.callsign,'Team plan');
 assert.equal(coOwned.plannedLaunchDate,'2027-03-01');
 assert.equal(coOwned.shareResearchData,false);
 // Restore synthetic membership and leave no records for later baseline checks.
 sql(`DELETE FROM public.devices WHERE owner_id='${owner}'; UPDATE community_private.official_team_members SET user_id=NULL WHERE user_id IN('${owner}','${outsider}'); DELETE FROM auth.users WHERE id IN('${owner}','${outsider}');`);
 console.log('PASS: planned registration, consent, regional drafts, co-ownership, validation and atomic rollback');
}
