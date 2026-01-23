-- Stratolink Mission Control Database Schema
-- Run this SQL in your Supabase SQL Editor to create the telemetry table

-- Create telemetry table for balloon tracking data
CREATE TABLE IF NOT EXISTS telemetry (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    device_id TEXT NOT NULL,
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    altitude_m DOUBLE PRECISION NOT NULL,
    velocity_x DOUBLE PRECISION,
    velocity_y DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on device_id for faster queries
CREATE INDEX IF NOT EXISTS idx_telemetry_device_id ON telemetry(device_id);

-- Create index on time for time-based queries
CREATE INDEX IF NOT EXISTS idx_telemetry_time ON telemetry(time DESC);

-- Create index on location for geospatial queries
CREATE INDEX IF NOT EXISTS idx_telemetry_location ON telemetry USING GIST (
    ST_MakePoint(lon, lat)
);

-- Create index on altitude for altitude-based filtering
CREATE INDEX IF NOT EXISTS idx_telemetry_altitude ON telemetry(altitude_m);

-- Create composite index for recent active balloons query
CREATE INDEX IF NOT EXISTS idx_telemetry_active ON telemetry(time DESC, device_id);

-- Enable Row Level Security (RLS)
ALTER TABLE telemetry ENABLE ROW LEVEL SECURITY;

-- Create policy to allow public read access
CREATE POLICY "Allow public read access" ON telemetry
    FOR SELECT
    USING (true);

-- Create policy to allow insert from authenticated users or service role
-- For webhook, you may want to use service role key instead
CREATE POLICY "Allow insert from service role" ON telemetry
    FOR INSERT
    WITH CHECK (true);

-- Create a view for latest telemetry per device (for active balloon tracking)
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
    created_at
FROM telemetry
ORDER BY device_id, time DESC;

-- Create a function to get active balloons (recent telemetry within specified time window)
CREATE OR REPLACE FUNCTION get_active_balloons(hours_ago INTEGER DEFAULT 1)
RETURNS TABLE (
    device_id TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    altitude_m DOUBLE PRECISION,
    last_seen TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (t.device_id)
        t.device_id,
        t.lat,
        t.lon,
        t.altitude_m,
        t.time AS last_seen
    FROM telemetry t
    WHERE t.time >= NOW() - (hours_ago || ' hours')::INTERVAL
    ORDER BY t.device_id, t.time DESC;
END;
$$ LANGUAGE plpgsql;
