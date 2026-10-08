import assert from 'node:assert/strict';

// Synthetic users and payloads in the disposable backend test database.
export async function checkOfficialTeam({ sql, service, denied, literal, hash }) {
  const members = ['30000000-0000-4000-8000-000000000001','30000000-0000-4000-8000-000000000002','30000000-0000-4000-8000-000000000003'];
  const outsider = '30000000-0000-4000-8000-000000000004';
  const ids = ['48384497','13071901','22897970'];
  sql(`INSERT INTO auth.users(id) VALUES ${[...members,outsider].map(id=>`('${id}')`).join(',')};`);
  const snapshot = () => sql("SELECT jsonb_agg(to_jsonb(d) ORDER BY d.device_id) FROM public.devices d WHERE device_id IN ('stratolink-2','stratolink-3')");
  const before = snapshot();
  for (const role of ['anon','authenticated']) {
    denied(`SET ROLE ${role}; SELECT public.sync_official_team_member('${outsider}','48384497');`);
    denied(`SET ROLE ${role}; SELECT * FROM community_private.official_team_members;`);
    denied(`SET ROLE ${role}; INSERT INTO community_private.team_balloons VALUES('forged');`);
    denied(`SET ROLE ${role}; SELECT community_private.can_manage_balloon('${outsider}','stratolink-3');`);
  }
  const sync = (id,githubId) => service(`SELECT public.sync_official_team_member('${id}','${githubId}');`);
  const account = id => JSON.parse(service(`SELECT public.community_account('${id}');`));
  const register = (id,login,eui) => JSON.parse(service(`SELECT public.register_community_balloon('${id}',${literal(login)},'Team review','${eui}');`));
  for (let i=0;i<3;i++) assert.equal(sync(members[i],ids[i]),'t');
  assert.equal(sync(outsider,'999000111'),'f');
  assert.deepEqual(account(outsider),[]);
  for (const member of members) {
    const balloons=account(member);
    assert.deepEqual(balloons.map(b=>b.id).sort(),['stratolink-2','stratolink-3']);
    assert.equal(balloons.every(b=>b.official && b.sharedWith.length===3),true);
    assert.equal(balloons.every(b=>b.ownerId===null),true);
  }
  assert.equal(snapshot(),before,'membership must not rewrite historical payload records');
  for (const device of ['stratolink-2','stratolink-3']) {
    const original=JSON.parse(before).find(d=>d.device_id===device).status;
    for (const member of members) {
      const changed=JSON.parse(service(`SELECT public.update_community_balloon('${member}','${device}','retired');`));
      assert.equal(changed.status,'retired');
      service(`SELECT public.update_community_balloon('${member}','${device}','${original}');`);
    }
    assert.equal(service(`SELECT public.update_community_balloon('${outsider}','${device}','flying') IS NULL;`),'t');
    assert.equal(service(`SELECT public.issue_payload_claim('${members[0]}','${device}','AABBCCDDEEFF1122','${hash('no-team-claim')}') IS NULL;`),'t');
    assert.equal(service(`SELECT public.claim_existing_payload('${outsider}','Twarner491','${device}','${hash('no-team-claim')}') IS NULL;`),'t');
  }
  const a=register(members[0],'renamed-github-account','1234567890AAAA01');
  const b=register(members[1],'clkruse','1234567890AAAA02');
  const c=JSON.parse(service(`SELECT public.reserve_community_payload('${members[2]}','ShepherdKruse','team-reservation');`));
  for(const item of [a,b,c])assert.equal(item.official,true);
  const fake=register(outsider,'Twarner491','1234567890AAAA03');
  assert.equal(fake.official,false);
  assert.deepEqual(fake.sharedWith,[]);
  for (const member of members) {
    assert.equal(account(member).length,5);
    assert.equal(service(`SELECT public.update_community_balloon('${member}','${fake.id}','landed') IS NULL;`),'t');
  }
  assert.equal(account(outsider).length,1);
  const connect=(owner,device,token)=>service(`SELECT public.connect_community_radio('${owner}','${device}','nam1','team-app','team-radio','1234567890AAAA01','US915','${hash(token)}');`);
  connect(members[0],a.id,'first-team-token');
  connect(members[1],a.id,'second-team-token');
  assert.equal(account(members[2]).find(d=>d.id===a.id).connections[0].managedBy,'owner');
  assert.equal(connect(outsider,a.id,'foreign-token'),'');
  assert.equal(service(`SELECT count(*) FROM public.resolve_ttn_ingress('${hash('first-team-token')}','team-app','team-radio','1234567890AAAA01');`),'0');
  assert.equal(service(`SELECT count(*) FROM public.resolve_ttn_ingress('${hash('second-team-token')}','team-app','team-radio','1234567890AAAA01');`),'1');
  // Co-ownership cannot rotate an integration shared with other payloads.
  sql(`UPDATE community_private.webhook_integrations SET owner_id=NULL WHERE token_hash='${hash('second-team-token')}';`);
  assert.throws(()=>connect(members[2],a.id,'do-not-rotate-shared-token'));
  assert.equal(service(`SELECT count(*) FROM public.resolve_ttn_ingress('${hash('second-team-token')}','team-app','team-radio','1234567890AAAA01');`),'1');
  // A current verified non-team GitHub identity revokes old membership mapping.
  assert.equal(sync(members[2],'999000112'),'f');
  assert.equal(account(members[2]).some(d=>d.id===a.id),false);
  assert.equal(sync(members[2],ids[2]),'t');
  console.log('PASS: all three verified GitHub accounts share historical and future official balloons; outsiders, copied names, direct RPCs and shared-token rotation are denied');
}
