-- Migration: Add UV, ambient light, and acoustic event columns; drop unused gyro columns
-- Matches firmware 35-byte telemetry payload (v2)

ALTER TABLE telemetry
ADD COLUMN IF NOT EXISTS uv_index INTEGER,
ADD COLUMN IF NOT EXISTS ambient_lux DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS acoustic_event INTEGER;

-- Drop unused gyro columns (no gyroscope on this board)
ALTER TABLE telemetry
DROP COLUMN IF EXISTS mems_gyro_x,
DROP COLUMN IF EXISTS mems_gyro_y,
DROP COLUMN IF EXISTS mems_gyro_z;

-- Update the latest_telemetry view
CREATE OR REPLACE VIEW latest_telemetry AS
SELECT DISTINCT ON (device_id)
    id,
    device_id,
    time,
    lat,
    lon,
    altitude_m,
    velocity_x,
    velocity_y,
    temperature,
    pressure,
    solar_voltage,
    battery_voltage,
    rssi,
    snr,
    gps_speed,
    gps_heading,
    gps_satellites,
    mems_accel_x,
    mems_accel_y,
    mems_accel_z,
    uv_index,
    ambient_lux,
    acoustic_event,
    created_at
FROM telemetry
ORDER BY device_id, time DESC;
