-- Migration 008: add device system-state columns so the dashboard can show
-- real firmware metadata (uptime, tx_count, power_mode, etc.) and LoRa link
-- characteristics (SF, bandwidth, frequency) instead of hardcoded placeholders.
--
-- All columns are nullable so old firmware payloads (and pre-existing rows)
-- continue to insert cleanly.

ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS firmware_version TEXT,
    ADD COLUMN IF NOT EXISTS uptime_s          INTEGER,
    ADD COLUMN IF NOT EXISTS tx_count          INTEGER,
    ADD COLUMN IF NOT EXISTS hdop              REAL,
    ADD COLUMN IF NOT EXISTS power_mode        TEXT,
    ADD COLUMN IF NOT EXISTS sleep_ms          INTEGER,
    ADD COLUMN IF NOT EXISTS lora_sf           INTEGER,
    ADD COLUMN IF NOT EXISTS lora_bw           INTEGER,
    ADD COLUMN IF NOT EXISTS frequency_hz      BIGINT;

COMMENT ON COLUMN telemetry.firmware_version IS 'Firmware semver string reported by the device, e.g. "2.1.4".';
COMMENT ON COLUMN telemetry.uptime_s         IS 'Seconds since device boot.';
COMMENT ON COLUMN telemetry.tx_count         IS 'Cumulative LoRaWAN uplink count since boot.';
COMMENT ON COLUMN telemetry.hdop             IS 'GPS HDOP (horizontal dilution of precision).';
COMMENT ON COLUMN telemetry.power_mode       IS 'Firmware-reported power tier: ACTIVE, IDLE, NOGPS, etc.';
COMMENT ON COLUMN telemetry.sleep_ms         IS 'Configured sleep duration between uplinks in milliseconds.';
COMMENT ON COLUMN telemetry.lora_sf          IS 'LoRa spreading factor for this uplink (extracted from TTN rx settings).';
COMMENT ON COLUMN telemetry.lora_bw          IS 'LoRa bandwidth in Hz for this uplink (e.g. 125000).';
COMMENT ON COLUMN telemetry.frequency_hz     IS 'LoRa carrier frequency in Hz for this uplink.';
