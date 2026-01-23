-- Flight Path Data for Stratolink Telemetry
-- This creates multiple telemetry points for each balloon to generate flight paths
-- Run this in Supabase SQL Editor to populate flight history

-- Delete old test data first (optional)
-- DELETE FROM telemetry WHERE device_id LIKE 'balloon-%';

-- Balloon 001: Flight path from New York to Atlantic
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-001', NOW() - INTERVAL '2 hours', 40.7128, -74.0060, 5000, 2.5, 1.5),
('balloon-001', NOW() - INTERVAL '1 hour 45 minutes', 40.8500, -73.9500, 8000, 3.0, 2.0),
('balloon-001', NOW() - INTERVAL '1 hour 30 minutes', 41.0000, -73.8500, 12000, 3.5, 2.5),
('balloon-001', NOW() - INTERVAL '1 hour 15 minutes', 41.1500, -73.7000, 15000, 4.0, 3.0),
('balloon-001', NOW() - INTERVAL '1 hour', 41.3000, -73.5000, 18000, 4.5, 3.5),
('balloon-001', NOW() - INTERVAL '45 minutes', 41.4500, -73.2000, 20000, 5.0, 4.0),
('balloon-001', NOW() - INTERVAL '30 minutes', 41.6000, -72.8000, 22000, 5.2, 4.2),
('balloon-001', NOW() - INTERVAL '15 minutes', 41.7000, -72.3000, 24000, 5.5, 4.5),
('balloon-001', NOW() - INTERVAL '5 minutes', 41.8000, -71.8000, 25000, 5.8, 4.8);

-- Balloon 002: Flight path from California to Nevada
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-002', NOW() - INTERVAL '2 hours', 34.0522, -118.2437, 6000, -1.5, 2.5),
('balloon-002', NOW() - INTERVAL '1 hour 45 minutes', 34.2000, -118.1000, 10000, -2.0, 3.0),
('balloon-002', NOW() - INTERVAL '1 hour 30 minutes', 34.3500, -117.9000, 14000, -2.2, 3.5),
('balloon-002', NOW() - INTERVAL '1 hour 15 minutes', 34.5000, -117.6500, 17000, -2.4, 4.0),
('balloon-002', NOW() - INTERVAL '1 hour', 34.6500, -117.3500, 20000, -2.5, 4.5),
('balloon-002', NOW() - INTERVAL '45 minutes', 34.8000, -117.0000, 22000, -2.6, 4.8),
('balloon-002', NOW() - INTERVAL '30 minutes', 34.9500, -116.6000, 24000, -2.7, 5.0),
('balloon-002', NOW() - INTERVAL '15 minutes', 35.1000, -116.1500, 26000, -2.8, 5.2),
('balloon-002', NOW() - INTERVAL '5 minutes', 35.2500, -115.7000, 28000, -2.9, 5.4);

-- Balloon 003: Flight path from Texas to Louisiana
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-003', NOW() - INTERVAL '2 hours', 29.7604, -95.3698, 4000, 1.0, -2.0),
('balloon-003', NOW() - INTERVAL '1 hour 45 minutes', 29.9000, -95.2000, 8000, 1.2, -2.5),
('balloon-003', NOW() - INTERVAL '1 hour 30 minutes', 30.0500, -95.0000, 12000, 1.3, -3.0),
('balloon-003', NOW() - INTERVAL '1 hour 15 minutes', 30.2000, -94.7500, 15000, 1.4, -3.2),
('balloon-003', NOW() - INTERVAL '1 hour', 30.3500, -94.4500, 18000, 1.5, -3.4),
('balloon-003', NOW() - INTERVAL '45 minutes', 30.5000, -94.1000, 20000, 1.6, -3.5),
('balloon-003', NOW() - INTERVAL '30 minutes', 30.6500, -93.7000, 22000, 1.7, -3.6),
('balloon-003', NOW() - INTERVAL '15 minutes', 30.8000, -93.2500, 24000, 1.8, -3.7),
('balloon-003', NOW() - INTERVAL '5 minutes', 30.9500, -92.8000, 25000, 1.9, -3.8);

-- Balloon 004: Flight path from Florida to Georgia
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-004', NOW() - INTERVAL '2 hours', 25.7617, -80.1918, 5000, 3.5, 1.8),
('balloon-004', NOW() - INTERVAL '1 hour 45 minutes', 26.0000, -80.0000, 9000, 3.7, 2.0),
('balloon-004', NOW() - INTERVAL '1 hour 30 minutes', 26.2500, -79.7500, 13000, 3.8, 2.1),
('balloon-004', NOW() - INTERVAL '1 hour 15 minutes', 26.5000, -79.4500, 16000, 3.9, 2.2),
('balloon-004', NOW() - INTERVAL '1 hour', 26.7500, -79.1000, 19000, 4.0, 2.3),
('balloon-004', NOW() - INTERVAL '45 minutes', 27.0000, -78.7000, 21000, 4.1, 2.4),
('balloon-004', NOW() - INTERVAL '30 minutes', 27.2500, -78.2500, 23000, 4.2, 2.5),
('balloon-004', NOW() - INTERVAL '15 minutes', 27.5000, -77.7500, 25000, 4.3, 2.6),
('balloon-004', NOW() - INTERVAL '5 minutes', 27.7500, -77.2000, 27000, 4.4, 2.7);

-- Balloon 005: Landing trajectory (descending)
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-005', NOW() - INTERVAL '3 hours', 39.8000, -75.3000, 15000, 0.5, 0.3),
('balloon-005', NOW() - INTERVAL '2 hours 45 minutes', 39.8500, -75.2500, 12000, 0.4, 0.2),
('balloon-005', NOW() - INTERVAL '2 hours 30 minutes', 39.9000, -75.2000, 9000, 0.3, 0.1),
('balloon-005', NOW() - INTERVAL '2 hours 15 minutes', 39.9300, -75.1800, 6000, 0.2, 0.1),
('balloon-005', NOW() - INTERVAL '2 hours', 39.9500, -75.1700, 3000, 0.1, 0.0),
('balloon-005', NOW() - INTERVAL '1 hour 45 minutes', 39.9520, -75.1660, 1500, 0.05, 0.0),
('balloon-005', NOW() - INTERVAL '1 hour 30 minutes', 39.9524, -75.1655, 800, 0.02, 0.0),
('balloon-005', NOW() - INTERVAL '1 hour 15 minutes', 39.9525, -75.1653, 400, 0.01, 0.0),
('balloon-005', NOW() - INTERVAL '1 hour', 39.9526, -75.1652, 200, 0.0, 0.0),
('balloon-005', NOW() - INTERVAL '45 minutes', 39.9526, -75.1652, 100, 0.0, 0.0),
('balloon-005', NOW() - INTERVAL '30 minutes', 39.9526, -75.1652, 50, 0.0, 0.0);

-- Balloon 006: Flight path over Atlantic Ocean
INSERT INTO telemetry (device_id, time, lat, lon, altitude_m, velocity_x, velocity_y) VALUES
('balloon-006', NOW() - INTERVAL '2 hours', 35.0, -50.0, 7000, 4.0, -1.5),
('balloon-006', NOW() - INTERVAL '1 hour 45 minutes', 35.2000, -49.5000, 11000, 4.2, -1.8),
('balloon-006', NOW() - INTERVAL '1 hour 30 minutes', 35.4000, -48.9000, 15000, 4.4, -2.0),
('balloon-006', NOW() - INTERVAL '1 hour 15 minutes', 35.6000, -48.2000, 18000, 4.5, -2.2),
('balloon-006', NOW() - INTERVAL '1 hour', 35.8000, -47.4000, 21000, 4.6, -2.3),
('balloon-006', NOW() - INTERVAL '45 minutes', 36.0000, -46.5000, 23000, 4.7, -2.4),
('balloon-006', NOW() - INTERVAL '30 minutes', 36.2000, -45.5000, 25000, 4.8, -2.5),
('balloon-006', NOW() - INTERVAL '15 minutes', 36.4000, -44.4000, 27000, 4.9, -2.6),
('balloon-006', NOW() - INTERVAL '5 minutes', 36.6000, -43.2000, 29000, 5.0, -2.7);

-- Verify the data was inserted
SELECT 
    device_id,
    COUNT(*) as data_points,
    MIN(time) as first_reading,
    MAX(time) as last_reading,
    AVG(altitude_m) as avg_altitude
FROM telemetry
WHERE device_id LIKE 'balloon-%'
GROUP BY device_id
ORDER BY device_id;
