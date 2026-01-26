-- Migration: Add comprehensive telemetry fields
-- Run this in Supabase SQL Editor to extend the telemetry table with all sensor data

-- Add new telemetry fields
ALTER TABLE telemetry
ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS pressure DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS solar_voltage DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS battery_voltage DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS rssi DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS snr DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS gps_speed DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS gps_heading DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS gps_satellites INTEGER,
ADD COLUMN IF NOT EXISTS mems_accel_x DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS mems_accel_y DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS mems_accel_z DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS mems_gyro_x DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS mems_gyro_y DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS mems_gyro_z DOUBLE PRECISION;

-- Add indexes for commonly queried fields
CREATE INDEX IF NOT EXISTS idx_telemetry_temperature ON telemetry(temperature);
CREATE INDEX IF NOT EXISTS idx_telemetry_pressure ON telemetry(pressure);
CREATE INDEX IF NOT EXISTS idx_telemetry_battery ON telemetry(battery_voltage);
CREATE INDEX IF NOT EXISTS idx_telemetry_rssi ON telemetry(rssi);

-- Update the latest_telemetry view to include new fields
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
    mems_gyro_x,
    mems_gyro_y,
    mems_gyro_z,
    created_at
FROM telemetry
ORDER BY device_id, time DESC;
