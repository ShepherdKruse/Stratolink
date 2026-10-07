import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function migration(name: string): string {
    return readFileSync(new URL(name, import.meta.url), 'utf8');
}

const wildlife = migration('009_wildlife_detections.sql');
const b2b = migration('010_b2b_packets.sql');
const integrity = migration('20260725090324_ttn_ingest_integrity.sql');
const cttAge = migration('20260725184000_ctt_detection_age.sql');
const telemetryV2 = migration('20260725222000_telemetry_observability_v2.sql');
const telemetryV3 = migration('20260831043000_telemetry_server_liveness_v3.sql');
const rawEvidence = migration('20261005194611_telemetry_raw_evidence.sql');
const readme = migration('README.md');
const legacyBootstrap = migration('../schema.sql');

// Public wildlife data is explicitly exposed read-only and protected by RLS.
assert.match(wildlife, /ENABLE ROW LEVEL SECURITY/i);
assert.match(wildlife, /GRANT SELECT ON TABLE wildlife_detections TO anon, authenticated/i);
assert.match(wildlife, /CREATE POLICY "Allow public read access"[\s\S]*FOR SELECT USING \(true\)/i);

// Raw authenticated B2B command material must remain service-only.
assert.match(b2b, /ENABLE ROW LEVEL SECURITY/i);
assert.match(b2b, /REVOKE ALL ON TABLE b2b_packets FROM anon, authenticated/i);
assert.match(b2b, /GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE b2b_packets TO service_role/i);
assert.doesNotMatch(b2b, /CREATE POLICY[\s\S]*USING \(true\)/i);
assert.match(b2b, /source_balloon_id BETWEEN 0 AND 65534/i);
assert.match(b2b, /ttl BETWEEN 0 AND 3/i);

// Harden the pre-existing public schema as well as newly created tables.
assert.match(integrity, /REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER[\s\S]*FROM anon, authenticated/i);
assert.match(integrity, /REVOKE SELECT ON TABLE public\.devices FROM anon, authenticated/i);
assert.match(integrity, /GRANT SELECT \([\s\S]*\) ON TABLE public\.devices TO anon, authenticated/i);
assert.match(integrity, /ALTER VIEW public\.latest_telemetry SET \(security_invoker = true\)/i);

// Wire versions must remain semantically distinguishable at the DB boundary.
assert.match(cttAge, /wildlife_detections_version_fields_check/i);
assert.match(telemetryV2, /telemetry_observability_version_fields_check/i);
assert.match(telemetryV2, /telemetry_version = 1[\s\S]*power_tier IS NULL/i);
assert.match(telemetryV2, /telemetry_version = 2[\s\S]*power_tier IS NOT NULL/i);
assert.match(telemetryV2, /gps_fix_age_min IS NULL OR gps_fix_age_min BETWEEN 0 AND 65534/i);
assert.match(telemetryV2, /telemetry_gps_state_check[\s\S]*gps_satellites = 0[\s\S]*gps_speed IS NULL[\s\S]*lat IS NOT NULL[\s\S]*gps_satellites IS NOT NULL[\s\S]*gps_satellites BETWEEN 4 AND 64[\s\S]*NOT VALID/i);
assert.equal(
    (telemetryV2.match(/ttn_device_id IS NULL OR/gi) ?? []).length,
    2,
    'v2 GPS and observability checks must both admit identity-null legacy writes during cutover'
);
assert.match(telemetryV2, /telemetry_observability_version_fields_check[\s\S]*ttn_device_id IS NULL OR[\s\S]*telemetry_version = 2[\s\S]*NOT VALID/i);
assert.ok(
    (telemetryV2.match(/NOT VALID/gi) ?? []).length >= 10,
    'v2 range/GPS/version checks must not scan and reject historical production drift'
);
assert.match(telemetryV2, /COMMENT ON COLUMN public\.telemetry\.acoustic_event/i);
assert.match(telemetryV2, /NULL legacy or microphone capture skipped\/failed/i);
assert.match(telemetryV2, /not FFT or source classification/i);
assert.match(telemetryV3, /telemetry_version IN \(1, 2, 3\)/i);
assert.match(telemetryV3, /telemetry_version = 2[\s\S]*server_proof_count_mod8 IS NULL/i);
assert.match(telemetryV3, /telemetry_version = 3[\s\S]*gps_fix_age_min BETWEEN 0 AND 510[\s\S]*server_proof_count_mod8 IS NOT NULL[\s\S]*server_qualified_miss_streak IS NOT NULL[\s\S]*server_recovery_parity IS NOT NULL/i);
assert.match(telemetryV3, /telemetry_observability_version_fields_check[\s\S]*ttn_device_id IS NULL OR[\s\S]*NOT VALID/i);
assert.ok(
    (telemetryV3.match(/NOT VALID/gi) ?? []).length >= 5,
    'v3 range/version checks must avoid historical validation scans during staging'
);
assert.match(telemetryV3, /server_proof_count_mod8 BETWEEN 0 AND 7/i);
assert.match(telemetryV3, /server_qualified_miss_streak BETWEEN 0 AND 3/i);
assert.match(telemetryV3, /server_recovery_parity IS NULL OR server_recovery_parity IN \(0, 1\)/i);

// New installs retain wire evidence without changing the existing gateway shape.
for (const [column, type] of [
    ['frm_payload', 'text'], ['f_port', 'smallint'],
    ['gateways', 'jsonb'], ['rx_metadata', 'jsonb'],
]) {
    assert.match(rawEvidence, new RegExp(`ADD COLUMN IF NOT EXISTS ${column} ${type}`, 'i'));
}
assert.doesNotMatch(rawEvidence, /\b(?:UPDATE|DELETE|DROP|TRUNCATE)\b/i);
assert.match(rawEvidence, /Normalized strongest-first gateway receptions/);
assert.match(rawEvidence, /Complete TTN rx_metadata array/);
assert.ok(readme.indexOf('`20261005194611_telemetry_raw_evidence.sql`') >
    readme.indexOf('`20260831043000_telemetry_server_liveness_v3.sql`'));

// The two legacy 005 files share a prefix but have a required explicit order.
const first005 = readme.indexOf('`005_acoustic_event.sql`');
const second005 = readme.indexOf('`005_add_uv_lux_acoustic.sql`');
assert.ok(first005 >= 0 && second005 > first005, 'legacy 005 migration order is missing or reversed');

// The original one-file bootstrap contains intentionally permissive historical
// policies. It must never again present itself as a complete production setup.
assert.match(legacyBootstrap, /LEGACY BOOTSTRAP ONLY/i);
assert.match(legacyBootstrap, /Do not run this file by itself/i);
assert.match(legacyBootstrap, /migrations\/README\.md/i);

console.log('Supabase migration RLS/grant/version/order contracts passed');
