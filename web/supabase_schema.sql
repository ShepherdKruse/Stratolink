-- Stratolink Telemetry Database Schema
-- Run this SQL in your Supabase SQL Editor to create the required tables

-- Create telemetry table
CREATE TABLE IF NOT EXISTS telemetry (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    device_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude DOUBLE PRECISION,
    battery_voltage DOUBLE PRECISION,
    temperature DOUBLE PRECISION,
    pressure DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on device_id for faster queries
CREATE INDEX IF NOT EXISTS idx_telemetry_device_id ON telemetry(device_id);

-- Create index on received_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_telemetry_received_at ON telemetry(received_at DESC);

-- Create index on location for geospatial queries (if using PostGIS)
-- CREATE INDEX IF NOT EXISTS idx_telemetry_location ON telemetry USING GIST (ST_MakePoint(longitude, latitude));

-- Enable Row Level Security (RLS)
ALTER TABLE telemetry ENABLE ROW LEVEL SECURITY;

-- Create policy to allow public read access (adjust as needed for your security requirements)
CREATE POLICY "Allow public read access" ON telemetry
    FOR SELECT
    USING (true);

-- Create policy to allow insert from authenticated users or service role
-- For webhook, you may want to use service role key instead
CREATE POLICY "Allow insert from service role" ON telemetry
    FOR INSERT
    WITH CHECK (true);

-- Optional: Create a view for latest telemetry per device
CREATE OR REPLACE VIEW latest_telemetry AS
SELECT DISTINCT ON (device_id)
    id,
    device_id,
    received_at,
    latitude,
    longitude,
    altitude,
    battery_voltage,
    temperature,
    pressure,
    created_at
FROM telemetry
ORDER BY device_id, received_at DESC;
