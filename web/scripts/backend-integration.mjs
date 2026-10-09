// Runs only against a disposable local PostgreSQL container with synthetic data.
import assert from 'node:assert/strict';
import { checkRegistrationPlanning } from './registration-planning-integration.mjs';
import { checkOfficialTeam } from './official-team-integration.mjs';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { readFileSync } from 'node:fs';
import { randomBytes, createHash } from 'node:crypto';
import { createTTNWebhook } from '../server/ttnWebhook.ts';
import { checkPayloadClaims } from './payload-claim-integration.mjs';

const exec = promisify(execFile);
const container = `stratolink-backend-${process.pid}-${randomBytes(4).toString('hex')}`;
const root = new URL('../../', import.meta.url);
const sqlArgs = ['exec', '-i', '-u', 'postgres', container, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-d', 'postgres'];
const sql = statement => execFileSync('docker', sqlArgs, { input: statement, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }).trim();
const service = statement => sql(`SET ROLE service_role; ${statement}`);
const literal = value => `'${String(value).replaceAll("'", "''")}'`;
const hash = value => createHash('sha256').update(value).digest('hex');
function denied(statement, pattern = /permission denied/) {
  let result;
  try { sql(statement); } catch (error) { result = error.stderr; }
  assert.match(result ?? '', pattern);
}
function insert(table, row) {
  assert.match(table, /^(telemetry|wildlife_detections|b2b_packets)$/);
  const columns = Object.keys(row).filter(key => row[key] !== undefined);
  columns.forEach(key => assert.match(key, /^[a-z_][a-z0-9_]*$/));
  return service(`INSERT INTO public.${table}(${columns.join(',')}) SELECT ${columns.join(',')} FROM jsonb_populate_record(NULL::public.${table},${literal(JSON.stringify(row))}::jsonb);`);
}
async function parallelSql(statement) {
  // psql -c is used for bounded synthetic queries only, never real credentials.
  return await exec('docker', [...sqlArgs, '-c', `SET ROLE service_role; ${statement}`]);
}
const owners = ['10000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000003'];

try {
  execFileSync('docker', ['run', '--rm', '-d', '--name', container, '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-p', '127.0.0.1::5432', '--tmpfs', '/var/lib/postgresql/data', 'postgres:17.6'], { stdio: 'pipe' });
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    try { execFileSync('docker', ['exec', container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], { stdio: 'pipe' }); ready = true; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 150)); }
  }
  assert.ok(ready, 'Disposable PostgreSQL did not start');
  sql(readFileSync(new URL('supabase/tests/baseline.sql', root), 'utf8'));
  for (const name of ['20261007003455_community_backend.sql', '20261007003501_telemetry_ingest_contract.sql', '20261007201932_payload_claim_compatibility.sql', '20261008194242_official_team_ownership.sql', '20261009030358_balloon_registration_planning.sql']) {
    sql(readFileSync(new URL(`supabase/migrations/${name}`, root), 'utf8'));
  }
  assert.equal(sql('SELECT count(*) FROM public.telemetry'), '1513');
  assert.equal(sql('SELECT count(*) FROM test_audit.original_telemetry b JOIN public.telemetry t USING(id) WHERE NOT to_jsonb(t) @> b.row'), '0');
  assert.equal(sql("SELECT count(*) FROM public.devices WHERE official AND connection_status='connected'"), '2');
  console.log('PASS: additive migration preserves every field of 1,513 legacy rows');

  for (const role of ['anon', 'authenticated']) {
    assert.equal(sql(`SET ROLE ${role}; SELECT count(device_id) FROM public.devices;`), '2');
    denied(`SET ROLE ${role}; SELECT owner_id FROM public.devices;`);
    denied(`SET ROLE ${role}; SELECT claim_code FROM public.devices;`);
    denied(`SET ROLE ${role}; SELECT * FROM public.devices;`);
    denied(`SET ROLE ${role}; SELECT * FROM community_private.webhook_integrations;`);
    denied(`SET ROLE ${role}; SELECT * FROM public.community_telemetry;`);
    denied(`SET ROLE ${role}; SELECT * FROM public.wildlife_detections;`);
    denied(`SET ROLE ${role}; SELECT * FROM public.b2b_packets;`);
    denied(`SET ROLE ${role}; SELECT public.community_account('${owners[0]}');`);
    denied(`SET ROLE ${role}; SELECT public.register_community_balloon('${owners[0]}','attacker','Forged','0011223344556677');`);
    denied(`SET ROLE ${role}; UPDATE public.devices SET official=true;`);
    denied(`SET ROLE ${role}; INSERT INTO public.telemetry(device_id,time) VALUES('forged',now());`);
  }
  console.log('PASS: anonymous and signed-in direct access cannot mutate or read private backend state');

  sql(`INSERT INTO auth.users(id) VALUES ${owners.map(id => `('${id}')`).join(',')};`);
  const balloon = (owner, name, eui) => JSON.parse(service(`SELECT public.register_community_balloon('${owner}','test-user',${literal(name)},'${eui}')`));
  const a = balloon(owners[0], 'Test balloon A', '0011223344556677');
  const b = balloon(owners[1], 'Test balloon B', '1122334455667788');
  assert.equal(a.connectionStatus, 'pending');
  assert.equal(sql('SET ROLE anon; SELECT count(device_id) FROM public.devices'), '2');
  assert.equal(service(`SELECT public.update_community_balloon('${owners[1]}','${a.id}','landed') IS NULL`), 't');
  assert.equal(service(`SELECT public.connect_community_radio('${owners[1]}','${a.id}','nam1','owner-app','same-device','0011223344556677','US915','${'a'.repeat(64)}') IS NULL`), 't');
  denied(`SET ROLE service_role; SELECT public.update_community_balloon('${owners[0]}','${a.id}','official');`, /Invalid status/);
  assert.equal(sql(`SELECT count(*) FROM public.community_telemetry WHERE device_id='${a.id}'`), '0');
  console.log('PASS: owner-scoped writes reject another user and pending registrations stay out of public telemetry');

  const firstSecret = 'integration-test-webhook-secret-original';
  const secondSecret = 'integration-test-webhook-secret-replacement';
  const connect = (owner, id, cluster, eui, token, app = 'owner-app', name = 'same-device') => service(`SELECT public.connect_community_radio('${owner}','${id}','${cluster}','${app}','${name}','${eui}','US915','${hash(token)}')`);
  connect(owners[0], a.id, 'nam1', '0011223344556677', firstSecret);
  connect(owners[1], b.id, 'eu1', '1122334455667788', secondSecret);
  const resolve = (token, app, name, eui) => JSON.parse(service(`SELECT coalesce(json_agg(r),'[]'::json) FROM public.resolve_ttn_ingress('${hash(token)}','${app}','${name}','${eui}') r`));
  assert.equal(resolve(firstSecret, 'owner-app', 'same-device', '0011223344556677')[0].canonical_device_id, a.id);
  assert.equal(resolve(secondSecret, 'owner-app', 'same-device', '1122334455667788')[0].canonical_device_id, b.id);
  assert.equal(resolve(firstSecret, 'other-app', 'same-device','0011223344556677').length, 0);
  for (const fields of [['owner-app','same-device-eu','0011223344556677'], ['owner-app','same-device','1122334455667788']]) {
    const rows = resolve(firstSecret, ...fields);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].identity_mismatch, true);
    assert.equal(rows[0].canonical_device_id, null);
  }
  assert.equal(resolve('unknown-integration-secret', 'owner-app', 'same-device', '0011223344556677').length, 0);
  console.log('PASS: scoped network identity prevents suffix guesses, cross-application and cross-owner collisions');

  let latestRow;
  const handler = createTTNWebhook({
    async resolveIdentity(lookup) {
      const rows = JSON.parse(service(`SELECT coalesce(json_agg(r),'[]'::json) FROM public.resolve_ttn_ingress(${Object.values(lookup).map(literal).join(',')}) r`));
      return rows[0] ?? null;
    },
    async insert(table, row) {
      latestRow = row;
      try { insert(table, row); return { error: null }; }
      catch (error) {
        const message = error.stderr ?? error.message;
        if (!message.includes('duplicate key')) console.error(message);
        return { error: { code: message.includes('duplicate key') ? '23505' : 'database', message } };
      }
    },
    async markReceived(id, time) {
      try { service(`SELECT public.mark_radio_received('${id}','${time}')`); return { error: null }; }
      catch (error) { return { error }; }
    },
  });
  const frame = Buffer.alloc(40); frame[35] = 7; frame.writeUInt16BE(0x91ff, 36);
  const payload = eui => ({
    end_device_ids: { device_id: 'same-device', application_ids: { application_id: 'owner-app' }, dev_eui: eui, dev_addr: '260CACD0' },
    received_at: '2026-10-06T12:00:00.123456Z',
    uplink_message: { f_port: 1, f_cnt: 7, frm_payload: frame.toString('base64'), rx_metadata: [] },
  });
  const receive = (token, input) => handler(new Request('https://stratolink.org/api/ttn-webhook', {
    method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' }, body: JSON.stringify(input),
  }));
  const unrelated = payload('AABBCCDDEEFF0011');
  unrelated.end_device_ids.device_id = 'unrelated-app-device';
  unrelated.uplink_message.f_port = 42;
  assert.equal((await receive(firstSecret, unrelated)).status, 202);
  assert.equal((await receive(firstSecret, payload('1122334455667788'))).status, 401);
  assert.equal(sql(`SELECT count(*) FROM public.telemetry WHERE device_id='${a.id}'`), '0');
  assert.equal((await receive(firstSecret, payload('0011223344556677'))).status, 200);
  assert.equal((await (await receive(firstSecret, payload('0011223344556677'))).json()).duplicate, true);
  assert.equal((await receive(secondSecret, payload('1122334455667788'))).status, 200);
  assert.equal(sql(`SELECT count(*) FROM public.telemetry WHERE device_id IN('${a.id}','${b.id}')`), '2');
  assert.equal(sql(`SELECT count(*) FROM public.community_telemetry WHERE device_id IN('${a.id}','${b.id}')`), '2');
  assert.equal(sql(`SELECT connection_status FROM public.devices WHERE device_id='${a.id}'`), 'connected');
  assert.equal(sql(`SELECT server_proof_count_mod8 FROM public.telemetry WHERE device_id='${a.id}'`), '1');
  const invalidV3 = { ...latestRow, ttn_received_at: '2026-10-06T12:01:00Z', server_proof_count_mod8: null };
  assert.throws(() => insert('telemetry', invalidV3));
  const partialIdentity = { ...latestRow, integration_id: null, ttn_received_at: '2026-10-06T12:02:00Z' };
  assert.throws(() => insert('telemetry', partialIdentity));
  console.log('PASS: actual webhook writes v3 evidence, confirms connection, deduplicates retries and preserves independent namespaces');

  // A shared legacy token may bind distinct applications, never an ambiguous
  // same-application cluster. New user connections always use random tokens.
  connect(owners[0], a.id, 'eu1', '0011223344556677', firstSecret, 'legacy-europe-app');
  assert.equal(resolve(firstSecret, 'legacy-europe-app', 'same-device', '0011223344556677')[0].canonical_device_id, a.id);
  assert.throws(() => connect(owners[0], a.id, 'au1', '0011223344556677', firstSecret));
  console.log('PASS: shared legacy tokens remain scoped to an unambiguous application identity');

  const replacement = 'integration-test-webhook-secret-rotated';
  connect(owners[0], a.id, 'nam1', '0011223344556677', replacement);
  assert.equal(resolve(firstSecret, 'owner-app', 'same-device', '0011223344556677').length, 0);
  assert.equal((await receive(firstSecret, payload('0011223344556677'))).status, 401);
  assert.equal(resolve(replacement, 'owner-app', 'same-device', '0011223344556677')[0].canonical_device_id, a.id);
  console.log('PASS: reconnect rotates the token and revoked tokens cannot ingest');

  service(`DO $$ BEGIN FOR i IN 1..49 LOOP PERFORM public.register_community_balloon('${owners[2]}','limit-user','Capacity test',upper(lpad(to_hex(i),16,'0'))); END LOOP; END $$;`);
  const registrationRace = await Promise.allSettled(Array.from({ length: 6 }, (_, i) => parallelSql(`SELECT public.register_community_balloon('${owners[2]}','limit-user','Concurrent test','${(100+i).toString(16).padStart(16,'0').toUpperCase()}');`)));
  assert.equal(registrationRace.filter(result => result.status === 'fulfilled').length, 1);
  assert.equal(sql(`SELECT count(*) FROM public.devices WHERE owner_id='${owners[2]}'`), '50');
  const radioRace = await Promise.allSettled([[owners[0], a.id], [owners[1], b.id]].map(([owner,id], i) => parallelSql(`SELECT public.connect_community_radio('${owner}','${id}','au1','race-app','race-device','AABBCCDDEEFF0011','AU915','${hash(`race-token-${i}`)}');`)));
  assert.equal(radioRace.filter(result => result.status === 'fulfilled').length, 1);
  assert.equal(sql("SELECT count(*) FROM community_private.radio_identities WHERE application_id='race-app'"), '1');
  console.log('PASS: concurrent registration limits and network-identity claims remain atomic');

  await checkPayloadClaims({ sql, service, denied, parallelSql, literal, hash });
  checkRegistrationPlanning({ sql, service, denied, literal });
  await checkOfficialTeam({ sql, service, denied, literal, hash });

  // Supabase extension objects have a different owner from its postgres role.
  // Reproduce that boundary so a warning-only REVOKE cannot pass unnoticed.
  sql(`CREATE ROLE extension_owner NOLOGIN; CREATE ROLE migration_operator NOLOGIN;
    ALTER TABLE public.spatial_ref_sys OWNER TO extension_owner;
    ALTER FUNCTION public.st_estimatedextent(text,text) OWNER TO extension_owner;
    GRANT ALL ON public.spatial_ref_sys TO migration_operator;
    GRANT EXECUTE ON FUNCTION public.st_estimatedextent(text,text) TO migration_operator;`);
  const postgisMigration = readFileSync(new URL('supabase/platform-hardening/20261007003602_restrict_postgis_client_access.sql', root), 'utf8');
  denied(`SET ROLE migration_operator; ${postgisMigration}`, /extension-owner privileges/);
  assert.equal(sql("SELECT has_table_privilege('anon','public.spatial_ref_sys','SELECT')"), 't');
  const applicationTables = ['devices','telemetry','uplink_events','latest_telemetry','community_telemetry','wildlife_detections','b2b_packets'];
  sql(applicationTables.map(table => `ALTER TABLE public.${table} OWNER TO migration_operator;`).join('\n') + `
    ALTER FUNCTION public.get_active_balloons(integer) OWNER TO migration_operator;
    GRANT USAGE ON SCHEMA community_private TO migration_operator;`);
  sql(`SET ROLE migration_operator; ${readFileSync(new URL('supabase/migrations/20261007225324_private_raw_data_cutover.sql', root), 'utf8')}`);
  for (const role of ['anon','authenticated']) {
    for (const table of applicationTables) {
      denied(`SET ROLE ${role}; SELECT * FROM public.${table};`);
    }
    denied(`SET ROLE ${role}; SELECT device_id FROM public.devices;`);
    denied(`SET ROLE ${role}; SELECT public.get_active_balloons(1);`);
  }
  assert.equal(sql("SELECT has_table_privilege('anon','public.spatial_ref_sys','SELECT')"), 't');
  assert.equal(sql("SET ROLE anon; SELECT public.st_estimatedextent('telemetry','lat')"), 'test');
  assert.equal((await receive(replacement, payload('0011223344556677'))).status, 200);
  assert.ok(Number(service('SELECT count(*) FROM public.community_telemetry')) > 1513);
  assert.equal(JSON.parse(service(`SELECT public.community_account('${owners[0]}')`))[0].id, a.id);
  assert.equal(sql('SELECT count(*) FROM test_audit.original_telemetry b JOIN public.telemetry t USING(id) WHERE NOT to_jsonb(t) @> b.row'), '0');
  console.log('PASS: explicit cutover closes raw tables, column grants, views and sensitive RPCs while server ingestion and accounts still work');

  // Separate extension-owner operation. The application cutover above already
  // succeeded without changing or escalating this platform-owned boundary.
  sql(postgisMigration);
  denied('SET ROLE anon; SELECT * FROM public.spatial_ref_sys;');
  denied("SET ROLE authenticated; SELECT public.st_estimatedextent('telemetry','lat');");
  assert.equal(service("SELECT public.st_estimatedextent('telemetry','lat')"), 'test');
  console.log('PASS: PostGIS hardening is independent, fails without owner authority and preserves service access');
  console.log('Backend integration checks passed. All data was synthetic.');
} finally {
  try { execFileSync('docker', ['rm', '-f', container], { stdio: 'pipe' }); } catch { /* Already removed. */ }
}
