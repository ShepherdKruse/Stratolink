-- Migration: Allow telemetry rows without a GPS fix (NOGPS power tier)
-- Some firmware power tiers transmit valid sensor data (battery, temp, pressure,
-- UV, lux, accelerometer, acoustic event) without a GPS position. We still want
-- to record those rows so we can see device health/uplink rate even before the
-- GPS first-fix.
--
-- Run this in Supabase SQL Editor after migrations 001..006.

ALTER TABLE telemetry
    ALTER COLUMN lat DROP NOT NULL,
    ALTER COLUMN lon DROP NOT NULL,
    ALTER COLUMN altitude_m DROP NOT NULL;

COMMENT ON COLUMN telemetry.lat IS 'Latitude in degrees. NULL when firmware reports no GPS fix.';
COMMENT ON COLUMN telemetry.lon IS 'Longitude in degrees. NULL when firmware reports no GPS fix.';
COMMENT ON COLUMN telemetry.altitude_m IS 'Altitude in meters. NULL when firmware reports no GPS fix.';
