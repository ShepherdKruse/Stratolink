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
        CHECK (telemetry_version IS NULL OR telemetry_version IN (1, 2)),
    ADD CONSTRAINT telemetry_power_tier_range
        CHECK (power_tier IS NULL OR power_tier BETWEEN 0 AND 4),
    ADD CONSTRAINT telemetry_reset_cause_range
        CHECK (reset_cause IS NULL OR reset_cause BETWEEN 0 AND 6),
    ADD CONSTRAINT telemetry_boot_count_range
        CHECK (boot_count IS NULL OR boot_count BETWEEN 0 AND 255),
    ADD CONSTRAINT telemetry_fix_age_range
        CHECK (gps_fix_age_min IS NULL OR gps_fix_age_min BETWEEN 0 AND 65534),
    ADD CONSTRAINT telemetry_command_ack_range
        CHECK (command_ack_seq IS NULL OR command_ack_seq BETWEEN 0 AND 255),
    ADD CONSTRAINT telemetry_relay_delta_range
        CHECK (relay_fwd_delta IS NULL OR relay_fwd_delta BETWEEN 0 AND 7),
    ADD CONSTRAINT telemetry_ctt_delta_range
        CHECK (ctt_tags_delta IS NULL OR ctt_tags_delta BETWEEN 0 AND 15),
    /* Firmware primary telemetry has only two GNSS states: an atomic NOGPS
     * sentinel, or a fully value-gated fix. Keep cached motion/coordinates
     * from being combined into a plausible-looking mixed database row. NOT
     * VALID deliberately avoids rewriting or rejecting historical Flight-3
     * evidence while still enforcing the constraint for every new insert. */
    ADD CONSTRAINT telemetry_gps_state_check CHECK (
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
    ADD CONSTRAINT telemetry_observability_version_fields_check CHECK (
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
    );

COMMENT ON COLUMN public.telemetry.gps_fix_age_min IS
    'Minutes since the firmware last accepted a fresh advancing GNSS PVT; NULL means no fix this boot or legacy v1';
COMMENT ON COLUMN public.telemetry.command_ack_seq IS
    'Last durably applied fPort-10 application sequence; NULL means no retained command acknowledgement';
COMMENT ON COLUMN public.telemetry.acoustic_event IS
    'Broadband DC-blocked acoustic-energy anomaly: 0 quiet, 1 event, NULL legacy or microphone capture skipped/failed; not FFT or source classification';
