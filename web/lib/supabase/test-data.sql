-- Test Data for Stratolink Telemetry
-- Run this in Supabase SQL Editor to add sample balloon telemetry

-- Delete old test data first (optional - comment out if you want to keep old data)
-- DELETE FROM telemetry WHERE device_id LIKE 'balloon-%';

-- Insert test balloons at various locations and altitudes with fresh timestamps
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
-- Active balloon over New York (recent, high altitude)
('balloon-001', NOW() - INTERVAL '30 minutes', 40.7128, -74.0060, 15000, 5.2, 3.1),

-- Active balloon over California (recent, high altitude)
('balloon-002', NOW() - INTERVAL '15 minutes', 34.0522, -118.2437, 18000, -2.5, 4.8),

-- Active balloon over Texas (very recent)
('balloon-003', NOW() - INTERVAL '5 minutes', 29.7604, -95.3698, 12000, 1.2, -3.5),

-- Active balloon over Florida (recent)
('balloon-004', NOW() - INTERVAL '45 minutes', 25.7617, -80.1918, 16000, 3.8, 2.1),

-- Landed balloon (low altitude, older but within 24 hours)
('balloon-005', NOW() - INTERVAL '3 hours', 39.9526, -75.1652, 50, 0, 0),

-- Active balloon over Atlantic (recent)
('balloon-006', NOW() - INTERVAL '20 minutes', 35.0, -50.0, 14000, 4.5, -2.3)
ON CONFLICT DO NOTHING;

-- Verify the data was inserted
SELECT 
    device_id,
    time,
    lat,
    lon,
    altitude_m,
    CASE 
        WHEN time >= NOW() - INTERVAL '1 hour' AND altitude_m > 100 THEN 'Active'
        WHEN altitude_m < 100 THEN 'Landed'
        ELSE 'Inactive'
    END as status
FROM telemetry
ORDER BY time DESC;
