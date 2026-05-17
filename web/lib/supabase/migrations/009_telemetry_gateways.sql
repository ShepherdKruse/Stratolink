-- Migration 009: capture the full per-uplink gateway list from TTN's rx_metadata
-- so we can show gateway diversity, triangulate without GPS, and visualise
-- coverage along the flight path.
--
-- The webhook currently extracts only rx_metadata[0].rssi / .snr (i.e. the
-- single strongest gateway) and discards the rest. Storing the full array as
-- JSONB lets us surface "heard by N gateways", per-gateway RSSI/SNR, and
-- gateway locations without changing the existing column shape.
--
-- Shape stored in `gateways` (one row per gateway, in TTN's order):
--   [
--     {
--       "gateway_id": "eui-323456abcdef",
--       "rssi":  -98.0,
--       "snr":     7.2,
--       "lat":   40.4,        -- only present when the gateway publishes location
--       "lon":  -79.9,
--       "alt":  250.0
--     },
--     ...
--   ]
--
-- Safety: this is an `ALTER TABLE ADD COLUMN` for a nullable column with no
-- default. In Postgres 11+ that's a catalog-only change — no row rewrite, no
-- table lock held beyond microseconds. Safe to run while the webhook is hot.
--
-- An index on `jsonb_array_length(gateways)` is intentionally NOT added here.
-- It would briefly take ACCESS EXCLUSIVE during the build; better to add it
-- later (with CREATE INDEX CONCURRENTLY) from a quieter moment if/when a
-- query actually needs it.

ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS gateways JSONB;

COMMENT ON COLUMN telemetry.gateways IS
    'Array of {gateway_id, rssi, snr, lat?, lon?, alt?} objects, one per gateway that received this uplink. Sourced from TTN rx_metadata.';
