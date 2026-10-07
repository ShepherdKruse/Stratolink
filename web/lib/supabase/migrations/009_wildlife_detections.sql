-- Typed CTT/Motus wildlife-tag detections from firmware fPort 11.
-- raw_tag_id is uint32 on air, so PostgreSQL bigint avoids signed overflow.
CREATE TABLE IF NOT EXISTS wildlife_detections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id text NOT NULL,
    time timestamptz NOT NULL,
    raw_tag_id bigint NOT NULL CHECK (raw_tag_id BETWEEN 0 AND 4294967295),
    motus_tag_id integer CHECK (motus_tag_id BETWEEN 0 AND 1048575),
    motus_valid boolean NOT NULL,
    detection_rssi smallint NOT NULL,
    hits smallint NOT NULL CHECK (hits BETWEEN 1 AND 255),
    listen_window integer NOT NULL CHECK (listen_window BETWEEN 0 AND 65535),
    link_rssi real,
    link_snr real,
    lora_sf smallint,
    lora_bw integer,
    frequency_hz bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wildlife_detections_device_time
    ON wildlife_detections (device_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_raw_tag_time
    ON wildlife_detections (raw_tag_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wildlife_detections_motus_tag_time
    ON wildlife_detections (motus_tag_id, time DESC)
    WHERE motus_valid;

ALTER TABLE wildlife_detections ENABLE ROW LEVEL SECURITY;

-- New Supabase platform defaults no longer expose newly-created public
-- tables automatically. Keep public clients read-only; the server-side
-- webhook uses service_role for inserts.
GRANT SELECT ON TABLE wildlife_detections TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE wildlife_detections TO service_role;

DROP POLICY IF EXISTS "Allow public read access" ON wildlife_detections;
CREATE POLICY "Allow public read access" ON wildlife_detections
    FOR SELECT USING (true);

COMMENT ON TABLE wildlife_detections IS
    'CTT LifeTag/PowerTag/HybridTag detections carried by StratoLink fPort 11';
