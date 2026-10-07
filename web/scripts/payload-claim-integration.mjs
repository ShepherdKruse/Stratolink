import assert from 'node:assert/strict';

// Invoked by backend-integration.mjs against its disposable synthetic database.
export async function checkPayloadClaims({ sql, service, denied, parallelSql, literal, hash }) {
  const ownerA = '20000000-0000-4000-8000-000000000001';
  const ownerB = '20000000-0000-4000-8000-000000000002';
  const staff = '20000000-0000-4000-8000-000000000003';
  const capacityOwner = '20000000-0000-4000-8000-000000000004';
  sql(`INSERT INTO auth.users(id) VALUES ('${ownerA}'),('${ownerB}'),('${staff}'),('${capacityOwner}');`);
  const eui = 'AABBCCDDEEFF1020';
  const otherEui = 'AABBCCDDEEFF1021';
  const reserve = (owner, name) => JSON.parse(service(`SELECT public.reserve_community_payload('${owner}','test-user',${literal(name)});`));
  const issue = (device, identity, token) => service(`SELECT public.issue_payload_claim('${staff}',${literal(device)},'${identity}','${hash(token)}');`);
  const claimSql = (owner, device, token) => `SELECT public.claim_existing_payload('${owner}','test-user',${literal(device)},'${hash(token)}');`;
  const claim = (owner, device, token) => service(claimSql(owner, device, token));
  const bind = (device, integration, identity = eui, name = device, cluster = 'nam1', app = 'staff-app') => service(`SELECT public.bind_staff_payload_radio(${literal(device)},'${integration}','${cluster}','${app}',${literal(name)},'${identity}','US915');`);
  const privateSnapshot = () => sql("SELECT jsonb_build_object('radios',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) FROM community_private.radio_identities r),'integrations',(SELECT jsonb_agg(to_jsonb(w) ORDER BY w.id) FROM community_private.webhook_integrations w))");

  for (const role of ['anon', 'authenticated']) {
    denied(`SET ROLE ${role}; SELECT * FROM community_private.payload_claims;`);
    denied(`SET ROLE ${role}; SELECT public.reserve_community_payload('${ownerA}','test-user','forged-reservation');`);
    denied(`SET ROLE ${role}; SELECT public.issue_payload_claim('${staff}','stratolink-3','${eui}','${hash('forged')}');`);
    denied(`SET ROLE ${role}; ${claimSql(ownerA, 'stratolink-3', 'forged')}`);
    denied(`SET ROLE ${role}; SELECT public.staff_payload_inventory();`);
    denied(`SET ROLE ${role}; SELECT public.bind_staff_payload_radio('stratolink-3','10000000-0000-4000-8000-000000000000','nam1','staff-app','device','${eui}','US915');`);
  }
  const owned = reserve(ownerA, 'workshop-reserved');
  assert.equal(owned.id, 'workshop-reserved');
  assert.equal(owned.status, 'planned');
  assert.equal(owned.devEui, null);
  assert.equal(owned.ownerId, ownerA);
  assert.equal(owned.connectionStatus, 'pending');
  assert.equal(sql("SELECT status FROM public.devices WHERE device_id='workshop-reserved'"), 'storage');
  denied(`SET ROLE service_role; SELECT public.reserve_community_payload('${ownerB}','test-user','workshop-reserved');`, /duplicate key/);
  denied(`SET ROLE service_role; SELECT public.reserve_community_payload('${ownerA}','test-user','INVALID');`, /Invalid reservation/);
  denied(`SET ROLE service_role; SELECT public.reserve_community_payload('${ownerA}','test-user','${'a'.repeat(37)}');`, /Invalid reservation/);
  assert.equal(issue('workshop-reserved', eui, 'cannot-claim-reservation'), '');
  console.log('PASS: callsign reservations keep stable IDs, remain owner-only and cannot reclaim an existing row');

  // A formerly exposed PIN and token hash can have arbitrary provenance.
  // Even a valid-looking future expiry must never establish account ownership.
  sql(`INSERT INTO public.devices(device_id,status,launcher_name,launch_lat,launch_lon,launched_at,claim_code,launch_token_hash,launch_token_expires_at,connection_status)
    VALUES ('workshop-legacy','landed','Original launcher',10,20,'2026-05-17T12:00:00Z','123456','${hash('old-exposed-token')}',now()+interval '1 day','connected');
    INSERT INTO public.telemetry(device_id,time,lat,lon,altitude_m) VALUES('workshop-legacy','2026-05-17T12:01:00Z',11,21,1500);`);
  assert.equal(claim(ownerA, 'workshop-legacy', '123456'), '');
  assert.equal(claim(ownerA, 'workshop-legacy', 'old-exposed-token'), '');
  assert.throws(() => issue('workshop-legacy', eui, 'unverified-proof'), /Command failed/);

  const integration = service(`INSERT INTO community_private.webhook_integrations(cluster,application_id,token_hash) VALUES('nam1','staff-app','${hash('shared-staff-token')}') RETURNING id;`);
  bind('workshop-legacy', integration);
  bind('workshop-reserved', integration, 'AABBCCDDEEFF1030');
  const ownedAfterBinding = JSON.parse(service(`SELECT public.community_account('${ownerA}')`)).find(item => item.id === owned.id);
  assert.equal(ownedAfterBinding.devEui, 'AABBCCDDEEFF1030');
  assert.equal(ownedAfterBinding.ownerId, ownerA);
  assert.equal(ownedAfterBinding.status, 'planned');
  assert.equal(ownedAfterBinding.connectionStatus, 'pending');
  const secondIntegration = service(`INSERT INTO community_private.webhook_integrations(cluster,application_id,token_hash) VALUES('eu1','staff-europe-app','${hash('shared-europe-token')}') RETURNING id;`);
  bind('workshop-legacy', secondIntegration, otherEui, 'workshop-europe', 'eu1', 'staff-europe-app');
  assert.equal(sql("SELECT dev_eui FROM community_private.balloon_registration WHERE device_id='workshop-legacy'"), eui);
  const beforeBindingRetry = privateSnapshot();
  bind('workshop-legacy', integration);
  assert.equal(privateSnapshot(), beforeBindingRetry);
  assert.throws(() => bind('workshop-reserved', integration, eui, 'workshop-legacy'));
  assert.throws(() => bind('workshop-legacy', integration, otherEui));
  assert.throws(() => bind('workshop-legacy', integration, eui, 'other-device'));
  assert.throws(() => bind('workshop-legacy', integration, eui, 'workshop-legacy', 'au1'));
  assert.equal(privateSnapshot(), beforeBindingRetry);
  const privateIntegration = service(`INSERT INTO community_private.webhook_integrations(owner_id,cluster,application_id,token_hash) VALUES('${ownerA}','nam1','owner-only-app','${hash('not-staff-token')}') RETURNING id;`);
  assert.throws(() => bind('workshop-legacy', privateIntegration, eui, 'workshop-legacy', 'nam1', 'owner-only-app'));
  const revokedIntegration = service(`INSERT INTO community_private.webhook_integrations(cluster,application_id,token_hash,revoked_at) VALUES('nam1','revoked-staff-app','${hash('revoked-staff-token')}',now()) RETURNING id;`);
  assert.throws(() => bind('workshop-legacy', revokedIntegration, eui, 'workshop-legacy', 'nam1', 'revoked-staff-app'));
  console.log('PASS: staff bindings preserve ownership, shared tokens and regional EUIs, rejecting collisions and unavailable integrations');

  issue('workshop-legacy', eui, 'first-fresh-proof');
  const issued = JSON.parse(issue('workshop-legacy', otherEui, 'replacement-proof'));
  assert.equal(issued.deviceId, 'workshop-legacy');
  assert.ok(Date.parse(issued.expiresAt) > Date.now() + 6 * 86400000);
  assert.equal(claim(ownerA, 'workshop-legacy', 'first-fresh-proof'), '');
  assert.equal(claim(ownerA, 'workshop-reserved', 'replacement-proof'), '');
  sql(`UPDATE community_private.payload_claims SET issued_at=now()-interval '8 days',expires_at=now()-interval '1 day'
    WHERE token_hash='${hash('replacement-proof')}';`);
  assert.equal(claim(ownerA, 'workshop-legacy', 'replacement-proof'), '');
  issue('workshop-legacy', otherEui, 'race-proof');
  const legacyBeforeClaim = sql("SELECT to_jsonb(d)-'owner_id'-'owner_github'-'updated_at' FROM public.devices d WHERE device_id='workshop-legacy'");
  const telemetryBeforeClaim = sql("SELECT md5(jsonb_agg(to_jsonb(t) ORDER BY id)::text) FROM public.telemetry t");
  const radiosBeforeClaim = privateSnapshot();
  const claims = await Promise.all([ownerA, ownerB].map(owner => parallelSql(claimSql(owner, 'workshop-legacy', 'race-proof'))));
  const successes = claims.filter(result => result.stdout.trim());
  assert.equal(successes.length, 1);
  const winner = JSON.parse(successes[0].stdout.trim());
  assert.equal(winner.id, 'workshop-legacy');
  assert.equal(winner.status, 'landed');
  assert.equal(winner.devEui, eui);
  assert.equal(winner.connections.length, 2);
  assert.equal(winner.connections.every(connection => connection.managedBy === 'stratolink'), true);
  assert.equal(sql("SELECT to_jsonb(d)-'owner_id'-'owner_github'-'updated_at' FROM public.devices d WHERE device_id='workshop-legacy'"), legacyBeforeClaim);
  assert.equal(sql("SELECT md5(jsonb_agg(to_jsonb(t) ORDER BY id)::text) FROM public.telemetry t"), telemetryBeforeClaim);
  assert.equal(privateSnapshot(), radiosBeforeClaim);
  assert.equal(claim(winner.ownerId, 'workshop-legacy', 'race-proof'), '');
  assert.equal(claim(winner.ownerId === ownerA ? ownerB : ownerA, 'workshop-legacy', 'race-proof'), '');
  assert.equal(issue('workshop-legacy', eui, 'owned-proof'), '');
  assert.equal(sql("SELECT count(*) FROM community_private.payload_claims WHERE device_id='workshop-legacy' AND consumed_at IS NOT NULL"), '1');
  assert.equal(JSON.parse(service(`SELECT public.community_account('${winner.ownerId}')`)).some(item => item.id === 'workshop-legacy'), true);
  assert.equal(service(`SELECT public.update_community_balloon('${winner.ownerId === ownerA ? ownerB : ownerA}','workshop-legacy','flying') IS NULL`), 't');
  const ownedStatus = JSON.parse(service(`SELECT public.update_community_balloon('${winner.ownerId}','workshop-legacy','missing')`));
  assert.equal(ownedStatus.id, 'workshop-legacy');
  assert.equal(ownedStatus.status, 'missing');
  assert.equal(ownedStatus.launchedAt, Date.parse('2026-05-17T12:00:00Z'));
  console.log('PASS: fresh one-time proofs rotate, expire and resolve competing claims atomically without changing flight records');

  denied(`SET ROLE service_role; SELECT public.connect_community_radio('${winner.ownerId}','workshop-legacy','nam1','staff-app','workshop-legacy','${eui}','US915','${hash('forbidden-owner-rotation')}');`, /managed by Stratolink/);
  assert.equal(privateSnapshot(), radiosBeforeClaim);
  assert.equal(service(`SELECT canonical_device_id FROM public.resolve_ttn_ingress('${hash('shared-staff-token')}','staff-app','workshop-reserved','AABBCCDDEEFF1030');`), 'workshop-reserved');
  const inventory = JSON.parse(service('SELECT public.staff_payload_inventory()'));
  assert.equal(inventory.payloads.find(item => item.deviceId === 'workshop-legacy').owned, true);
  assert.equal(inventory.payloads.find(item => item.deviceId === 'workshop-reserved').launcherName, null);
  assert.equal(inventory.integrations.some(item => item.id === integration), true);
  assert.equal(inventory.integrations.some(item => item.id === privateIntegration || item.id === revokedIntegration), false);
  const inventoryText = JSON.stringify(inventory);
  for (const sensitive of ['token_hash', 'claim_code', 'ownerId', 'owner_id', hash('shared-staff-token'), hash('race-proof'), ownerA, ownerB]) assert.equal(inventoryText.includes(sensitive), false);
  console.log('PASS: claiming a payload cannot rotate a shared webhook, and staff inventory excludes proof hashes and owner IDs');

  const selfConnected = reserve(ownerA, 'self-connected');
  const connection = JSON.parse(service(`SELECT public.connect_community_radio('${ownerA}','${selfConnected.id}','nam1','self-connect-app','self-radio','AABBCCDDEEFF1050','US915','${hash('self-verified-token')}');`));
  assert.equal(connection.devEui, 'AABBCCDDEEFF1050');
  assert.equal(connection.connections.length, 1);
  assert.equal(connection.connections[0].managedBy, 'owner');
  assert.equal(connection.status, 'planned');
  assert.equal(connection.connectionStatus, 'pending');
  console.log('PASS: verified owner connections populate a reserved payload without starting its flight');

  for (const action of ['claim', 'reserve', 'issue']) {
    for (let i = 0; i < 5; i++) assert.equal(service(`SELECT public.community_rate_limit('${staff}','${action}')`), 't');
    assert.equal(service(`SELECT public.community_rate_limit('${staff}','${action}')`), 'f');
  }
  service(`DO $$ BEGIN FOR i IN 1..49 LOOP PERFORM public.reserve_community_payload('${capacityOwner}','capacity-user','capacity-'||i); END LOOP; END $$;`);
  sql("INSERT INTO public.devices(device_id,status) VALUES('capacity-claim','storage');");
  bind('capacity-claim', integration, 'AABBCCDDEEFF1099');
  issue('capacity-claim', 'AABBCCDDEEFF1099', 'capacity-proof');
  const capacityRace = await Promise.allSettled([
    parallelSql(`SELECT public.reserve_community_payload('${capacityOwner}','capacity-user','capacity-final');`),
    parallelSql(`SELECT public.register_community_balloon('${capacityOwner}','capacity-user','Capacity registration','AABBCCDDEEFF1098');`),
    parallelSql(claimSql(capacityOwner, 'capacity-claim', 'capacity-proof')),
  ]);
  assert.equal(capacityRace.filter(result => result.status === 'fulfilled').length, 1);
  assert.equal(sql(`SELECT count(*) FROM public.devices WHERE owner_id='${capacityOwner}'`), '50');
  console.log('PASS: reservations, registration and existing-payload claims share the same atomic account limit');
}
