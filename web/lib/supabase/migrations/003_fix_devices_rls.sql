-- Fix: Add RLS policies for devices table
-- This migration fixes the issue where devices cannot be auto-created in development mode
-- Run this in Supabase SQL Editor if you're getting "device not found" errors

-- Enable Row Level Security (RLS) if not already enabled
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (to avoid conflicts)
DROP POLICY IF EXISTS "Allow public read access" ON devices;
DROP POLICY IF EXISTS "Allow insert for activation" ON devices;
DROP POLICY IF EXISTS "Allow update for activation" ON devices;

-- Create policy to allow public read access
CREATE POLICY "Allow public read access" ON devices
    FOR SELECT
    USING (true);

-- Create policy to allow insert (for device activation)
CREATE POLICY "Allow insert for activation" ON devices
    FOR INSERT
    WITH CHECK (true);

-- Create policy to allow update (for device activation and status changes)
CREATE POLICY "Allow update for activation" ON devices
    FOR UPDATE
    USING (true)
    WITH CHECK (true);

-- Verify the policies were created
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE tablename = 'devices';
