-- Exact authenticated version-3 B2B frames heard by one balloon and tunneled through its
-- LoRaWAN link on fPort 12.  A source/message pair may legitimately reappear
-- through multiple gateway balloons, so retain each reception.
CREATE TABLE IF NOT EXISTS b2b_packets (
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
    ON b2b_packets (gateway_balloon_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_b2b_packets_source_time
    ON b2b_packets (source_balloon_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_b2b_packets_source_message
    ON b2b_packets (source_balloon_id, message_id);

ALTER TABLE b2b_packets ENABLE ROW LEVEL SECURITY;

-- Raw authenticated frames include replayable command material. Keep the
-- table service-only; a future public track view may expose decoded crumbs
-- without raw frames, tags, or command bodies.
REVOKE ALL ON TABLE b2b_packets FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE b2b_packets TO service_role;

DROP POLICY IF EXISTS "Allow public read access" ON b2b_packets;

COMMENT ON TABLE b2b_packets IS
    'Authenticated StratoLink B2B wire-v3 frames received over LongFast and tunneled on LoRaWAN fPort 12; service-only because raw commands are replayable';
