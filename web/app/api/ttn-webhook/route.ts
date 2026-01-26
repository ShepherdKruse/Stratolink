import { NextRequest, NextResponse } from 'next/server';
import { createServiceRoleClient } from '@/lib/supabase';
import { parseTTNPayload, type TTNWebhookPayload } from '@/lib/ttn/payload-parser';

export async function POST(request: NextRequest) {
    try {
        const payload: TTNWebhookPayload = await request.json();
        
        // Parse telemetry data from TTN webhook payload
        const telemetry = parseTTNPayload(payload);
        
        if (!telemetry) {
            console.error('Failed to parse TTN payload:', JSON.stringify(payload, null, 2));
            return NextResponse.json(
                { error: 'Invalid payload: could not parse telemetry data' },
                { status: 400 }
            );
        }

        // Validate required fields
        if (!telemetry.device_id || telemetry.lat === 0 || telemetry.lon === 0) {
            console.error('Invalid telemetry data:', telemetry);
            return NextResponse.json(
                { error: 'Invalid payload: missing required fields (device_id, lat, lon)' },
                { status: 400 }
            );
        }

        // Check if device exists and is activated (optional validation)
        const supabase = createServiceRoleClient();
        const { data: device } = await supabase
            .from('devices')
            .select('device_id, status')
            .eq('device_id', telemetry.device_id)
            .single();

        // Log warning for unknown devices but don't block (allows testing)
        if (!device) {
            console.warn(`Telemetry received from unknown device: ${telemetry.device_id}`);
        } else if (device.status !== 'flying') {
            console.warn(`Telemetry received from device not in 'flying' status: ${telemetry.device_id} (status: ${device.status})`);
        }

        // Insert telemetry into Supabase
        const { error } = await supabase
            .from('telemetry')
            .insert({
                device_id: telemetry.device_id,
                time: telemetry.time,
                lat: telemetry.lat,
                lon: telemetry.lon,
                altitude_m: telemetry.altitude_m,
                velocity_x: telemetry.velocity_x,
                velocity_y: telemetry.velocity_y,
                temperature: telemetry.temperature,
                pressure: telemetry.pressure,
                solar_voltage: telemetry.solar_voltage,
                battery_voltage: telemetry.battery_voltage,
                rssi: telemetry.rssi,
                snr: telemetry.snr,
                gps_speed: telemetry.gps_speed,
                gps_heading: telemetry.gps_heading,
                gps_satellites: telemetry.gps_satellites,
                mems_accel_x: telemetry.mems_accel_x,
                mems_accel_y: telemetry.mems_accel_y,
                mems_accel_z: telemetry.mems_accel_z,
                mems_gyro_x: telemetry.mems_gyro_x,
                mems_gyro_y: telemetry.mems_gyro_y,
                mems_gyro_z: telemetry.mems_gyro_z,
            });
        
        if (error) {
            console.error('Supabase insert error:', error);
            return NextResponse.json(
                { error: 'Database insert failed', details: error.message },
                { status: 500 }
            );
        }

        console.log(`Telemetry inserted for device ${telemetry.device_id} at ${telemetry.lat}, ${telemetry.lon}`);
        
        return NextResponse.json({ 
            success: true,
            device_id: telemetry.device_id 
        }, { status: 200 });
        
    } catch (error) {
        console.error('Webhook processing error:', error);
        return NextResponse.json(
            { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
            { status: 500 }
        );
    }
}
