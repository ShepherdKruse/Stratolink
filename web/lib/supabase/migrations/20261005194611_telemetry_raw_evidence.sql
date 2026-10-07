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
