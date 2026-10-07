-- Additive ingest contract for the existing Stratolink telemetry archive.
-- Run after community_backend. Historical telemetry is never rewritten.
-- The live baseline contains telemetry/devices; new empty installations must
-- restore that baseline before applying these deployment migrations.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS public.wildlife_detections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id text NOT NULL,
    time timestamptz NOT NULL,
    event_version smallint NOT NULL CHECK (event_version IN (1, 2)),
    detected_at timestamptz,
    detection_age_min integer CHECK (detection_age_min BETWEEN 0 AND 65535),
    raw_tag_id bigint NOT NULL CHECK (raw_tag_id BETWEEN 0 AND 4294967295),
    motus_tag_id integer CHECK (motus_tag_id BETWEEN 0 AND 1048575),
    motus_valid boolean NOT NULL,
    detection_rssi smallint NOT NULL,
    hits smallint NOT NULL CHECK (hits BETWEEN 1 AND 255),
    listen_window integer CHECK (listen_window BETWEEN 0 AND 65535),
    link_rssi real,
    link_snr real,
    lora_sf smallint,
    lora_bw integer,
    frequency_hz bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT wildlife_detections_version_fields_check CHECK (
        (event_version = 1 AND listen_window IS NOT NULL AND detection_age_min IS NULL AND detected_at IS NULL) OR
        (event_version = 2 AND listen_window IS NULL AND detection_age_min IS NOT NULL AND detected_at IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_device_time ON public.wildlife_detections (device_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_raw_tag_time ON public.wildlife_detections (raw_tag_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_motus_tag_time ON public.wildlife_detections (motus_tag_id, time DESC) WHERE motus_valid;
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_detected_time ON public.wildlife_detections (device_id, detected_at DESC) WHERE detected_at IS NOT NULL;

-- Exact authenticated version-3 B2B frames heard by one balloon and tunneled through its
-- LoRaWAN link on fPort 12.  A source/message pair may legitimately reappear
-- through multiple gateway balloons, so retain each reception.
CREATE TABLE IF NOT EXISTS public.b2b_packets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gateway_balloon_id text NOT NULL,
    time timestamptz NOT NULL,
    source_balloon_id integer NOT NULL CHECK (source_balloon_id BETWEEN 0 AND 65534),
    message_id smallint NOT NULL CHECK (message_id BETWEEN 0 AND 255),
    ttl smallint NOT NULL CHECK (ttl BETWEEN 0 AND 3),
    frame_type text NOT NULL CHECK (frame_type IN ('crumb', 'command', 'ack')),
    payload_base64 text NOT NULL,
    raw_frame_base64 text NOT NULL,
    crumbs jsonb,
    command_target integer CHECK (command_target BETWEEN 0 AND 65535),
    command_opcode smallint CHECK (command_opcode BETWEEN 0 AND 255),
    command_seq smallint CHECK (command_seq BETWEEN 0 AND 255),
    link_rssi real,
    link_snr real,
    lora_sf smallint,
    lora_bw integer,
    frequency_hz bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_b2b_packets_gateway_time
    ON public.b2b_packets (gateway_balloon_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_b2b_packets_source_time
    ON public.b2b_packets (source_balloon_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_b2b_packets_source_message
    ON public.b2b_packets (source_balloon_id, message_id);


ALTER TABLE public.wildlife_detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.b2b_packets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.wildlife_detections, public.b2b_packets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.wildlife_detections, public.b2b_packets TO service_role;


ALTER TABLE public.telemetry
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text,
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint,
    ADD COLUMN IF NOT EXISTS integration_id uuid REFERENCES community_private.webhook_integrations(id),
    ADD COLUMN IF NOT EXISTS radio_identity_id uuid REFERENCES community_private.radio_identities(id);
ALTER TABLE public.telemetry
    ADD CONSTRAINT telemetry_dev_addr_check CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$') NOT VALID,
    ADD CONSTRAINT telemetry_frame_counter_check CHECK (f_cnt BETWEEN 0 AND 4294967295) NOT VALID,
    ADD CONSTRAINT telemetry_ingest_identity_check CHECK ((
        (integration_id IS NULL AND radio_identity_id IS NULL) OR
        (integration_id IS NOT NULL AND radio_identity_id IS NOT NULL AND
         ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL AND
         (dev_addr IS NOT NULL OR session_key_id IS NOT NULL))
    ) IS TRUE) NOT VALID;
-- Keep old retry keys only for legacy, integration-less ingestion. Otherwise
-- identical device names in separate TTN applications collide before the new
-- namespace-aware index can apply.
DROP INDEX IF EXISTS public.idx_telemetry_ttn_delivery;
CREATE UNIQUE INDEX idx_telemetry_ttn_delivery
    ON public.telemetry (ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NULL AND ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL;

ALTER TABLE public.wildlife_detections
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text,
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint,
    ADD COLUMN IF NOT EXISTS integration_id uuid REFERENCES community_private.webhook_integrations(id),
    ADD COLUMN IF NOT EXISTS radio_identity_id uuid REFERENCES community_private.radio_identities(id);
ALTER TABLE public.wildlife_detections
    ADD CONSTRAINT wildlife_detections_dev_addr_check CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$') NOT VALID,
    ADD CONSTRAINT wildlife_detections_frame_counter_check CHECK (f_cnt BETWEEN 0 AND 4294967295) NOT VALID,
    ADD CONSTRAINT wildlife_detections_ingest_identity_check CHECK ((
        (integration_id IS NULL AND radio_identity_id IS NULL) OR
        (integration_id IS NOT NULL AND radio_identity_id IS NOT NULL AND
         ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL AND
         (dev_addr IS NOT NULL OR session_key_id IS NOT NULL))
    ) IS TRUE) NOT VALID;
-- Keep old retry keys only for legacy, integration-less ingestion. Otherwise
-- identical device names in separate TTN applications collide before the new
-- namespace-aware index can apply.
DROP INDEX IF EXISTS public.idx_wildlife_detections_ttn_delivery;
CREATE UNIQUE INDEX idx_wildlife_detections_ttn_delivery
    ON public.wildlife_detections (ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NULL AND ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL;

ALTER TABLE public.b2b_packets
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text,
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint,
    ADD COLUMN IF NOT EXISTS integration_id uuid REFERENCES community_private.webhook_integrations(id),
    ADD COLUMN IF NOT EXISTS radio_identity_id uuid REFERENCES community_private.radio_identities(id);
ALTER TABLE public.b2b_packets
    ADD CONSTRAINT b2b_packets_dev_addr_check CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$') NOT VALID,
    ADD CONSTRAINT b2b_packets_frame_counter_check CHECK (f_cnt BETWEEN 0 AND 4294967295) NOT VALID,
    ADD CONSTRAINT b2b_packets_ingest_identity_check CHECK ((
        (integration_id IS NULL AND radio_identity_id IS NULL) OR
        (integration_id IS NOT NULL AND radio_identity_id IS NOT NULL AND
         ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL AND
         (dev_addr IS NOT NULL OR session_key_id IS NOT NULL))
    ) IS TRUE) NOT VALID;
-- Keep old retry keys only for legacy, integration-less ingestion. Otherwise
-- identical device names in separate TTN applications collide before the new
-- namespace-aware index can apply.
DROP INDEX IF EXISTS public.idx_b2b_packets_ttn_delivery;
CREATE UNIQUE INDEX idx_b2b_packets_ttn_delivery
    ON public.b2b_packets (ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NULL AND ttn_device_id IS NOT NULL AND ttn_received_at IS NOT NULL AND f_cnt IS NOT NULL;

CREATE UNIQUE INDEX telemetry_ttn_scoped_delivery
    ON public.telemetry (integration_id, ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NOT NULL;
CREATE INDEX telemetry_radio_identity_idx ON public.telemetry (radio_identity_id) WHERE radio_identity_id IS NOT NULL;

CREATE UNIQUE INDEX wildlife_ttn_scoped_delivery
    ON public.wildlife_detections (integration_id, ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NOT NULL;
CREATE INDEX wildlife_detections_radio_identity_idx ON public.wildlife_detections (radio_identity_id) WHERE radio_identity_id IS NOT NULL;

CREATE UNIQUE INDEX b2b_ttn_scoped_delivery
    ON public.b2b_packets (integration_id, ttn_device_id, ttn_received_at, f_cnt)
    WHERE integration_id IS NOT NULL;
CREATE INDEX b2b_packets_radio_identity_idx ON public.b2b_packets (radio_identity_id) WHERE radio_identity_id IS NOT NULL;

-- Match the existing production evidence columns on new installations.
-- Nullable, additive fields preserve historical rows and legacy JSON input.
ALTER TABLE public.telemetry
    ADD COLUMN IF NOT EXISTS frm_payload text,
    ADD COLUMN IF NOT EXISTS f_port smallint,
    ADD COLUMN IF NOT EXISTS gateways jsonb,
    ADD COLUMN IF NOT EXISTS rx_metadata jsonb;

COMMENT ON COLUMN public.telemetry.frm_payload IS
    'Exact base64 TTN FRMPayload retained for later offline decoding; NULL for decoded-only legacy input';
COMMENT ON COLUMN public.telemetry.f_port IS
    'TTN application port associated with the retained FRMPayload';
COMMENT ON COLUMN public.telemetry.gateways IS
    'Normalized strongest-first gateway receptions with gateway_id, rssi, snr, lat, lon, and alt';
COMMENT ON COLUMN public.telemetry.rx_metadata IS
    'Complete TTN rx_metadata array, preserving all receiving gateways and their RF measurements';

-- Length-gated 40-byte primary telemetry v2. All columns remain nullable so
-- historical 35-byte v1 rows and regional rollout overlap remain valid.
ALTER TABLE public.telemetry
    ADD COLUMN IF NOT EXISTS telemetry_version SMALLINT,
    ADD COLUMN IF NOT EXISTS power_tier SMALLINT,
    ADD COLUMN IF NOT EXISTS reset_cause SMALLINT,
    ADD COLUMN IF NOT EXISTS boot_count SMALLINT,
    ADD COLUMN IF NOT EXISTS gps_fix_age_min INTEGER,
    ADD COLUMN IF NOT EXISTS command_ack_seq SMALLINT,
    ADD COLUMN IF NOT EXISTS relay_enabled BOOLEAN,
    ADD COLUMN IF NOT EXISTS relay_fwd_delta SMALLINT,
    ADD COLUMN IF NOT EXISTS ctt_tags_delta SMALLINT;

ALTER TABLE public.telemetry
    DROP CONSTRAINT IF EXISTS telemetry_version_range,
    DROP CONSTRAINT IF EXISTS telemetry_power_tier_range,
    DROP CONSTRAINT IF EXISTS telemetry_reset_cause_range,
    DROP CONSTRAINT IF EXISTS telemetry_boot_count_range,
    DROP CONSTRAINT IF EXISTS telemetry_fix_age_range,
    DROP CONSTRAINT IF EXISTS telemetry_command_ack_range,
    DROP CONSTRAINT IF EXISTS telemetry_relay_delta_range,
    DROP CONSTRAINT IF EXISTS telemetry_ctt_delta_range,
    DROP CONSTRAINT IF EXISTS telemetry_gps_state_check,
    DROP CONSTRAINT IF EXISTS telemetry_observability_version_fields_check,
    ADD CONSTRAINT telemetry_version_range
        CHECK (telemetry_version IS NULL OR telemetry_version IN (1, 2))
        NOT VALID,
    ADD CONSTRAINT telemetry_power_tier_range
        CHECK (power_tier IS NULL OR power_tier BETWEEN 0 AND 4)
        NOT VALID,
    ADD CONSTRAINT telemetry_reset_cause_range
        CHECK (reset_cause IS NULL OR reset_cause BETWEEN 0 AND 6)
        NOT VALID,
    ADD CONSTRAINT telemetry_boot_count_range
        CHECK (boot_count IS NULL OR boot_count BETWEEN 0 AND 255)
        NOT VALID,
    ADD CONSTRAINT telemetry_fix_age_range
        CHECK (gps_fix_age_min IS NULL OR gps_fix_age_min BETWEEN 0 AND 65534)
        NOT VALID,
    ADD CONSTRAINT telemetry_command_ack_range
        CHECK (command_ack_seq IS NULL OR command_ack_seq BETWEEN 0 AND 255)
        NOT VALID,
    ADD CONSTRAINT telemetry_relay_delta_range
        CHECK (relay_fwd_delta IS NULL OR relay_fwd_delta BETWEEN 0 AND 7)
        NOT VALID,
    ADD CONSTRAINT telemetry_ctt_delta_range
        CHECK (ctt_tags_delta IS NULL OR ctt_tags_delta BETWEEN 0 AND 15)
        NOT VALID,
    /* Firmware primary telemetry has only two GNSS states: an atomic NOGPS
     * sentinel, or a fully value-gated fix. Keep cached motion/coordinates
     * from being combined into a plausible-looking mixed database row. NOT
     * VALID deliberately avoids rewriting or rejecting historical Flight-3
     * evidence while enforcing the strict contract for every identity-bearing
     * insert from the hardened route. */
    ADD CONSTRAINT telemetry_gps_state_check CHECK (
        /* The pre-authentication production route does not write TTN delivery
         * identity. Keep those rows admissible while this schema is staged;
         * the hardened route always writes ttn_device_id and is held to the
         * strict two-state GNSS contract below. */
        ttn_device_id IS NULL OR
        (lat IS NULL AND lon IS NULL AND altitude_m IS NULL AND
         (gps_satellites IS NULL OR gps_satellites = 0) AND
         gps_speed IS NULL AND gps_heading IS NULL AND
         velocity_x IS NULL AND velocity_y IS NULL) OR
        (lat IS NOT NULL AND lon IS NOT NULL AND altitude_m IS NOT NULL AND
         gps_satellites IS NOT NULL AND gps_speed IS NOT NULL AND
         gps_heading IS NOT NULL AND velocity_x IS NOT NULL AND
         velocity_y IS NOT NULL AND
         lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180 AND
         altitude_m BETWEEN -500 AND 60000 AND
         gps_satellites BETWEEN 4 AND 64 AND
         gps_speed BETWEEN 0 AND 500 AND
         gps_heading >= 0 AND gps_heading < 360 AND
         velocity_x BETWEEN -500 AND 500 AND
         velocity_y BETWEEN -500 AND 500)
    ) NOT VALID,
    -- CHECK accepts NULL; version coherence must evaluate explicitly true.
    ADD CONSTRAINT telemetry_observability_version_fields_check CHECK ((
        /* This identity-null transition branch is what permits a zero-loss
         * schema-first rollout. Once the authenticated route is live, every
         * accepted delivery carries ttn_device_id and must match a strict
         * version branch. */
        ttn_device_id IS NULL OR
        (telemetry_version IS NULL AND
         power_tier IS NULL AND reset_cause IS NULL AND boot_count IS NULL AND
         gps_fix_age_min IS NULL AND command_ack_seq IS NULL AND
         relay_enabled IS NULL AND relay_fwd_delta IS NULL AND
         ctt_tags_delta IS NULL) OR
        (telemetry_version = 1 AND
         power_tier IS NULL AND reset_cause IS NULL AND boot_count IS NULL AND
         gps_fix_age_min IS NULL AND command_ack_seq IS NULL AND
         relay_enabled IS NULL AND relay_fwd_delta IS NULL AND
         ctt_tags_delta IS NULL) OR
        (telemetry_version = 2 AND
         power_tier IS NOT NULL AND reset_cause IS NOT NULL AND
         boot_count IS NOT NULL AND relay_enabled IS NOT NULL AND
         relay_fwd_delta IS NOT NULL AND ctt_tags_delta IS NOT NULL)
    ) IS TRUE) NOT VALID;

COMMENT ON COLUMN public.telemetry.gps_fix_age_min IS
    'Minutes since the firmware last accepted a fresh advancing GNSS PVT; NULL means no fix this boot or legacy v1';
COMMENT ON COLUMN public.telemetry.command_ack_seq IS
    'Last durably applied fPort-10 application sequence; NULL means no retained command acknowledgement';
COMMENT ON COLUMN public.telemetry.acoustic_event IS
    'Broadband DC-blocked acoustic-energy anomaly: 0 quiet, 1 event, NULL legacy or microphone capture skipped/failed; not FFT or source classification';

-- The current 40-byte primary reuses bytes 36-37 for bounded LoRaWAN
-- server/session-liveness evidence. Legacy telemetry-v2 rows remain valid and
-- keep the historical full-width fix-age interpretation.
ALTER TABLE public.telemetry
    ADD COLUMN IF NOT EXISTS server_proof_count_mod8 SMALLINT,
    ADD COLUMN IF NOT EXISTS server_qualified_miss_streak SMALLINT,
    ADD COLUMN IF NOT EXISTS server_recovery_parity SMALLINT;

ALTER TABLE public.telemetry
    DROP CONSTRAINT IF EXISTS telemetry_version_range,
    DROP CONSTRAINT IF EXISTS telemetry_server_proof_range,
    DROP CONSTRAINT IF EXISTS telemetry_server_miss_range,
    DROP CONSTRAINT IF EXISTS telemetry_server_recovery_parity_range,
    DROP CONSTRAINT IF EXISTS telemetry_observability_version_fields_check,
    ADD CONSTRAINT telemetry_version_range
        CHECK (telemetry_version IS NULL OR telemetry_version IN (1, 2, 3))
        NOT VALID,
    ADD CONSTRAINT telemetry_server_proof_range CHECK (
        server_proof_count_mod8 IS NULL OR
        server_proof_count_mod8 BETWEEN 0 AND 7
    ) NOT VALID,
    ADD CONSTRAINT telemetry_server_miss_range CHECK (
        server_qualified_miss_streak IS NULL OR
        server_qualified_miss_streak BETWEEN 0 AND 3
    ) NOT VALID,
    ADD CONSTRAINT telemetry_server_recovery_parity_range CHECK (
        server_recovery_parity IS NULL OR server_recovery_parity IN (0, 1)
    ) NOT VALID,
    /* Production contains pre-v3 rows decoded by an older TTN formatter as
     * telemetry_version=2 while some later v2 columns are NULL. Preserve that
     * historical transport evidence and the old route's schema-first cutover
     * writes without weakening identity-bearing writes: PostgreSQL enforces a
     * NOT VALID CHECK for every new/updated row, but does not scan and reject
     * already-stored legacy drift during deployment. */
    -- CHECK accepts NULL; version coherence must evaluate explicitly true.
    ADD CONSTRAINT telemetry_observability_version_fields_check CHECK ((
        /* Identity-null rows are produced only by the pre-authentication
         * route. This branch lets that route continue ingesting between the
         * schema and web deployments. The hardened route requires and writes
         * ttn_device_id, so every post-cutover row is held to the strict
         * version-specific branches below. */
        ttn_device_id IS NULL OR
        (telemetry_version IS NULL AND
         power_tier IS NULL AND reset_cause IS NULL AND boot_count IS NULL AND
         gps_fix_age_min IS NULL AND command_ack_seq IS NULL AND
         relay_enabled IS NULL AND relay_fwd_delta IS NULL AND
         ctt_tags_delta IS NULL AND server_proof_count_mod8 IS NULL AND
         server_qualified_miss_streak IS NULL AND
         server_recovery_parity IS NULL) OR
        (telemetry_version = 1 AND
         power_tier IS NULL AND reset_cause IS NULL AND boot_count IS NULL AND
         gps_fix_age_min IS NULL AND command_ack_seq IS NULL AND
         relay_enabled IS NULL AND relay_fwd_delta IS NULL AND
         ctt_tags_delta IS NULL AND server_proof_count_mod8 IS NULL AND
         server_qualified_miss_streak IS NULL AND
         server_recovery_parity IS NULL) OR
        (telemetry_version = 2 AND
         power_tier IS NOT NULL AND reset_cause IS NOT NULL AND
         boot_count IS NOT NULL AND relay_enabled IS NOT NULL AND
         relay_fwd_delta IS NOT NULL AND ctt_tags_delta IS NOT NULL AND
         server_proof_count_mod8 IS NULL AND
         server_qualified_miss_streak IS NULL AND
         server_recovery_parity IS NULL) OR
        (telemetry_version = 3 AND
         power_tier IS NOT NULL AND reset_cause IS NOT NULL AND
         boot_count IS NOT NULL AND relay_enabled IS NOT NULL AND
         relay_fwd_delta IS NOT NULL AND ctt_tags_delta IS NOT NULL AND
         (gps_fix_age_min IS NULL OR gps_fix_age_min BETWEEN 0 AND 510) AND
         server_proof_count_mod8 IS NOT NULL AND
         server_qualified_miss_streak IS NOT NULL AND
         server_recovery_parity IS NOT NULL)
    ) IS TRUE) NOT VALID;

COMMENT ON COLUMN public.telemetry.server_proof_count_mod8 IS
    'Authenticated LoRaWAN server/session proof counter modulo 8; telemetry v3 only';
COMMENT ON COLUMN public.telemetry.server_qualified_miss_streak IS
    'Consecutive fully qualified confirmed-probe misses, 0 through 3; telemetry v3 only';
COMMENT ON COLUMN public.telemetry.server_recovery_parity IS
    'Completed same-region session-recovery count modulo 2; telemetry v3 only';

CREATE INDEX IF NOT EXISTS telemetry_device_time_id_idx ON public.telemetry (device_id, time, id);

-- The application sanitizes coordinates and limits columns before returning
-- rows. This service-only view additionally makes disconnected or pending
-- balloons inaccessible through that public telemetry endpoint.
CREATE OR REPLACE VIEW public.community_telemetry WITH (security_invoker = true) AS
SELECT t.* FROM public.telemetry t
INNER JOIN public.devices d ON d.device_id = t.device_id
WHERE d.connection_status = 'connected';
REVOKE ALL ON TABLE public.community_telemetry FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.community_telemetry TO service_role;
COMMIT;
