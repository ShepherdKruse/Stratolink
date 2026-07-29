-- Authenticate TTN at the application boundary, then make each accepted
-- uplink idempotent at the database boundary. TTN may retry webhook delivery,
-- and the Storage Integration is also the recovery source while webhook
-- retries are disabled. Current StratoLink manual-session records contain no
-- session_key_id or correlation_ids, so neither can be required.
--
-- TTN's Application Server received_at is stable for an exact webhook retry
-- or Storage replay. The regional TTN device ID, that server timestamp, and
-- FCntUp therefore identify a delivery without suppressing a later real frame
-- after a manual-session FCnt reset. DevAddr and optional session ID remain
-- available for audit and session grouping.
--
-- Columns remain nullable so historical rows can coexist without an unsafe
-- guessed backfill. The webhook requires all retry-key fields for new rows.
ALTER TABLE public.telemetry
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text
        CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$'),
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint
        CHECK (f_cnt BETWEEN 0 AND 4294967295);

ALTER TABLE public.wildlife_detections
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text
        CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$'),
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint
        CHECK (f_cnt BETWEEN 0 AND 4294967295);

ALTER TABLE public.b2b_packets
    ADD COLUMN IF NOT EXISTS ttn_device_id text,
    ADD COLUMN IF NOT EXISTS dev_addr text
        CHECK (dev_addr IS NULL OR dev_addr ~ '^[0-9A-F]{8}$'),
    ADD COLUMN IF NOT EXISTS session_key_id text,
    ADD COLUMN IF NOT EXISTS ttn_received_at timestamptz,
    ADD COLUMN IF NOT EXISTS f_cnt bigint
        CHECK (f_cnt BETWEEN 0 AND 4294967295);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_ttn_delivery
    ON public.telemetry (ttn_device_id, ttn_received_at, f_cnt)
    WHERE ttn_device_id IS NOT NULL
        AND ttn_received_at IS NOT NULL
        AND f_cnt IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_wildlife_detections_ttn_delivery
    ON public.wildlife_detections (ttn_device_id, ttn_received_at, f_cnt)
    WHERE ttn_device_id IS NOT NULL
        AND ttn_received_at IS NOT NULL
        AND f_cnt IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_b2b_packets_ttn_delivery
    ON public.b2b_packets (ttn_device_id, ttn_received_at, f_cnt)
    WHERE ttn_device_id IS NOT NULL
        AND ttn_received_at IS NOT NULL
        AND f_cnt IS NOT NULL;

COMMENT ON COLUMN public.telemetry.ttn_device_id IS
    'Raw regional TTN device ID before StratoLink canonicalization';
COMMENT ON COLUMN public.telemetry.dev_addr IS
    'Normalized LoRaWAN DevAddr observed by TTN for session audit';
COMMENT ON COLUMN public.telemetry.session_key_id IS
    'Optional TTN Join Server session ID; absent for manual sessions';
COMMENT ON COLUMN public.telemetry.ttn_received_at IS
    'TTN Application Server timestamp used with device ID and FCntUp for idempotency';
COMMENT ON COLUMN public.telemetry.f_cnt IS
    'TTN LoRaWAN FCntUp used with device ID and server timestamp for idempotent ingestion';

-- The web application performs every mutation through a server-side
-- service-role client.  Legacy development policies allowed any anon client
-- to create or rewrite launch records and telemetry, including claim codes.
DROP POLICY IF EXISTS "Allow insert from service role" ON public.telemetry;
DROP POLICY IF EXISTS "Allow insert for activation" ON public.devices;
DROP POLICY IF EXISTS "Allow update for activation" ON public.devices;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.telemetry, public.devices,
        public.wildlife_detections, public.b2b_packets
    FROM anon, authenticated;

-- Do not expose claim codes or launch-token hashes through the Data API.
REVOKE SELECT ON TABLE public.devices FROM anon, authenticated;
GRANT SELECT (
    device_id,
    status,
    launcher_name,
    launch_lat,
    launch_lon,
    launched_at,
    created_at,
    updated_at
) ON TABLE public.devices TO anon, authenticated;

GRANT SELECT ON TABLE public.telemetry, public.wildlife_detections
    TO anon, authenticated;
REVOKE SELECT ON TABLE public.b2b_packets FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON TABLE public.telemetry, public.devices,
        public.wildlife_detections, public.b2b_packets
    TO service_role;

-- Views are security-definer by default in PostgreSQL.  Make the public view
-- obey the querying role's RLS and grants instead of its creator's privileges.
ALTER VIEW public.latest_telemetry SET (security_invoker = true);
GRANT SELECT ON TABLE public.latest_telemetry TO anon, authenticated;
