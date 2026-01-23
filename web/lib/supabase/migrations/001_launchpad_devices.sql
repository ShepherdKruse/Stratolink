-- Migration: Launchpad Device Activation System
-- Adds fields to support device claiming and launch tracking

-- Note: This migration assumes devices table may or may not exist
-- If devices table doesn't exist, create it first
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'devices') THEN
        CREATE TABLE devices (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    END IF;
END $$;

-- Add new columns for launchpad functionality
ALTER TABLE devices
ADD COLUMN IF NOT EXISTS claim_code TEXT,
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'storage',
ADD COLUMN IF NOT EXISTS launcher_name TEXT,
ADD COLUMN IF NOT EXISTS launch_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS launch_lon DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS launched_at TIMESTAMPTZ;

-- Create index on claim_code for fast lookups
CREATE INDEX IF NOT EXISTS idx_devices_claim_code ON devices(claim_code) WHERE claim_code IS NOT NULL;

-- Create index on status for filtering
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);

-- Add constraint to ensure status is one of valid values
ALTER TABLE devices
DROP CONSTRAINT IF EXISTS devices_status_check;

ALTER TABLE devices
ADD CONSTRAINT devices_status_check 
CHECK (status IN ('storage', 'flying', 'landed', 'retired'));

-- Add comment for documentation
COMMENT ON COLUMN devices.claim_code IS '6-digit PIN code for device activation';
COMMENT ON COLUMN devices.status IS 'Device status: storage, flying, landed, retired';
COMMENT ON COLUMN devices.launcher_name IS 'Name of person who launched the device';
COMMENT ON COLUMN devices.launch_lat IS 'Latitude of launch location';
COMMENT ON COLUMN devices.launch_lon IS 'Longitude of launch location';
COMMENT ON COLUMN devices.launched_at IS 'Timestamp when device was activated/launched';

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_devices_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS devices_updated_at_trigger ON devices;
CREATE TRIGGER devices_updated_at_trigger
    BEFORE UPDATE ON devices
    FOR EACH ROW
    EXECUTE FUNCTION update_devices_updated_at();
