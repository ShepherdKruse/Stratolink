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
