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
assert.match(telemetryV2, /COMMENT ON COLUMN public\.telemetry\.acoustic_event/i);
assert.match(telemetryV2, /NULL legacy or microphone capture skipped\/failed/i);
assert.match(telemetryV2, /not FFT or source classification/i);

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
