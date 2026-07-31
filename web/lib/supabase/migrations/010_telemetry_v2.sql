-- Migration 010: telemetry-v2 (StratoLink-2 40-byte packet) + non-telemetry uplinks
--
-- StratoLink-2 firmware sends a 40-byte fPort-1 packet ("telemetry v2"):
--   * Bytes 0-33 are identical to the v1 35-byte layout (GPS, env, power,
--     motion, UV, light) — already decoded correctly today.
--   * Byte 34 is now a PACKED STATUS BYTE (power tier, reset cause, relay
--     state). Under the v1 parser it has been landing in `acoustic_event`,
--     which is why bench rows show values like 224/160 there.
--   * Bytes 35-39 add boot count, GPS-fix age, command ACK, relay activity
--     and wildlife (CTT) tag counts.
--   * Wildlife detections arrive on fPort 11, balloon-to-balloon (B2B)
--     relay packets on fPort 12 — neither is position telemetry and neither
--     must be decoded as such.
--
-- The exact bit layout of the packed status byte and byte 39 is owned by the
-- firmware (Teddy); until it is confirmed the webhook stores the RAW packet
-- (frm_payload) and raw status_byte alongside the fields it can decode
-- unambiguously, so every v2 field is retroactively recoverable by a backfill.
--
-- Safety: nullable ADD COLUMNs with no default — catalog-only in Postgres 11+,
-- no row rewrite, safe to run while the webhook is hot. Idempotent.

-- ---- TTN identity / raw-packet columns (every uplink) ----
ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS f_port            SMALLINT,
    ADD COLUMN IF NOT EXISTS frm_payload       TEXT,      -- base64, exactly as received from TTN
    ADD COLUMN IF NOT EXISTS telemetry_version SMALLINT;  -- 1 = 35-byte, 2 = 40-byte; NULL for legacy rows

-- ---- v2 fields decodable today ----
ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS status_byte SMALLINT,  -- raw byte 34 (packed: power tier / reset cause / relay state)
    ADD COLUMN IF NOT EXISTS boot_count  SMALLINT;  -- byte 35

-- ---- v2 fields pending firmware bit-layout confirmation ----
-- Populated by the webhook once the packed layout is confirmed, and/or by a
-- backfill over `frm_payload`. A TTN payload formatter (decoded_payload)
-- populates them immediately, bypassing the ambiguity.
ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS power_tier      SMALLINT,
    ADD COLUMN IF NOT EXISTS reset_cause     SMALLINT,
    ADD COLUMN IF NOT EXISTS gps_fix_age_min INTEGER,
    ADD COLUMN IF NOT EXISTS command_ack_seq INTEGER,
    ADD COLUMN IF NOT EXISTS relay_enabled   BOOLEAN,
    ADD COLUMN IF NOT EXISTS relay_fwd_delta SMALLINT,
    ADD COLUMN IF NOT EXISTS ctt_tags_delta  SMALLINT;

COMMENT ON COLUMN telemetry.f_port            IS 'LoRaWAN fPort of the uplink (1 = primary telemetry).';
COMMENT ON COLUMN telemetry.frm_payload       IS 'Raw base64 frame payload as received from TTN — source of truth for backfills.';
COMMENT ON COLUMN telemetry.telemetry_version IS '1 = 35-byte v1 packet, 2 = 40-byte StratoLink-2 packet. NULL for rows ingested before this migration.';
COMMENT ON COLUMN telemetry.status_byte       IS 'Raw v2 byte 34: packed power tier / reset cause / relay state. Decode into the typed columns once the firmware bit layout is confirmed.';

-- ---- Non-telemetry uplinks: wildlife (fPort 11) and B2B relay (fPort 12) ----
-- Stored raw so no data is lost while their formats are finalised; decoding
-- can happen later without asking the balloon to retransmit.
CREATE TABLE IF NOT EXISTS uplink_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id   TEXT NOT NULL,
    time        TIMESTAMPTZ NOT NULL,
    f_port      SMALLINT NOT NULL,
    frm_payload TEXT,            -- base64 as received
    rssi        DOUBLE PRECISION,
    snr         DOUBLE PRECISION,
    gateways    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS uplink_events_device_time_idx
    ON uplink_events (device_id, time DESC);

COMMENT ON TABLE uplink_events IS
    'Raw non-telemetry uplinks (fPort 11 = wildlife/CTT detections, fPort 12 = balloon-to-balloon relay). Kept undecoded until formats are finalised.';

-- Same access model as telemetry: service-role writes (webhook), public reads.
ALTER TABLE uplink_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'uplink_events' AND policyname = 'uplink_events_public_read'
    ) THEN
        CREATE POLICY uplink_events_public_read ON uplink_events
            FOR SELECT USING (true);
    END IF;
END $$;
