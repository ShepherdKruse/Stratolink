-- Test Devices for Development
-- Run this SQL in Supabase SQL Editor to create test devices

-- Insert test devices with claim codes
INSERT INTO devices (device_id, claim_code, status)
VALUES 
    ('balloon-001', '123456', 'storage'),
    ('balloon-002', '234567', 'storage'),
    ('balloon-003', '345678', 'storage'),
    ('balloon-042', '042042', 'storage'),
    ('balloon-test', '000000', 'storage')
ON CONFLICT (device_id) DO UPDATE
SET claim_code = EXCLUDED.claim_code,
    status = EXCLUDED.status;

-- Verify devices were created
SELECT device_id, claim_code, status, created_at 
FROM devices 
ORDER BY created_at DESC;
