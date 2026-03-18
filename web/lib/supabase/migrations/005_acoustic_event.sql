-- Add acoustic_event from MEMS mic + FFT change detection (byte 37 in firmware payload)
ALTER TABLE telemetry
ADD COLUMN IF NOT EXISTS acoustic_event SMALLINT;

COMMENT ON COLUMN telemetry.acoustic_event IS '0 = no event, non-zero = spectral change detected (mic FFT vs baseline)';

CREATE INDEX IF NOT EXISTS idx_telemetry_acoustic_event ON telemetry(acoustic_event) WHERE acoustic_event IS NOT NULL AND acoustic_event != 0;

-- Update latest_telemetry view
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
    acoustic_event,
    created_at
FROM telemetry
ORDER BY device_id, time DESC;
