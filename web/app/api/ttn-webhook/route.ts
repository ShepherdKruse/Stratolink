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

        /* device_id is the only hard requirement. lat/lon may be null when the
         * firmware is in NOGPS power tier — we still want the sensor data row.
         * The dashboard map query filters null positions out so this is safe. */
        if (!telemetry.device_id) {
            console.error('Invalid telemetry data: missing device_id', telemetry);
            return NextResponse.json(
                { error: 'Invalid payload: missing required field device_id' },
                { status: 400 }
            );
        }

        const hasGpsFix = telemetry.lat !== null && telemetry.lon !== null;

        /* Normalize per-region TTN device IDs to a single canonical
         * identifier.  The firmware uses up to 4 distinct (DevEUI, AppKey)
         * pairs — one per LoRaWAN region — registered on TTN with IDs
         * like `stratolink-3`, `stratolink-3-eu`, `stratolink-3-as`,
         * `stratolink-3-au`.  Strip the trailing region suffix so all
         * streams land in Supabase under one device row and the
         * dashboard shows a single continuous timeline across regional
         * handovers.  The raw TTN device_id is preserved in log lines
         * and the success response for debugging. */
        const canonical_device_id = telemetry.device_id.replace(/-(eu|as|au)$/, '');

        // Check if device exists and is activated (optional validation)
        const supabase = createServiceRoleClient();
        const { data: device } = await supabase
            .from('devices')
            .select('device_id, status')
            .eq('device_id', canonical_device_id)
            .single();

        // Log warning for unknown devices but don't block (allows testing)
        if (!device) {
            console.warn(`Telemetry received from unknown device: ${canonical_device_id} (TTN ID: ${telemetry.device_id})`);
        } else if (device.status !== 'flying') {
            console.warn(`Telemetry received from device not in 'flying' status: ${canonical_device_id} (status: ${device.status})`);
        }

        const { error } = await supabase
            .from('telemetry')
            .insert({
                device_id: canonical_device_id,
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
                uv_index: telemetry.uv_index,
                ambient_lux: telemetry.ambient_lux,
                acoustic_event: telemetry.acoustic_event,
                firmware_version: telemetry.firmware_version,
                uptime_s: telemetry.uptime_s,
                tx_count: telemetry.tx_count,
                hdop: telemetry.hdop,
                power_mode: telemetry.power_mode,
                sleep_ms: telemetry.sleep_ms,
                lora_sf: telemetry.lora_sf,
                lora_bw: telemetry.lora_bw,
                frequency_hz: telemetry.frequency_hz,
            });

        if (error) {
            console.error('Supabase insert error:', error);
            return NextResponse.json(
                { error: 'Database insert failed', details: error.message },
                { status: 500 }
            );
        }

        if (hasGpsFix) {
            console.log(`Telemetry inserted for ${canonical_device_id} (TTN: ${telemetry.device_id}) at ${telemetry.lat}, ${telemetry.lon}`);
        } else {
            console.log(`Telemetry inserted for ${canonical_device_id} (TTN: ${telemetry.device_id}; no GPS fix, sensor-only row)`);
        }

        return NextResponse.json({
            success: true,
            device_id: canonical_device_id,
            ttn_device_id: telemetry.device_id,
            gps_fix: hasGpsFix,
        }, { status: 200 });

    } catch (error) {
        console.error('Webhook processing error:', error);
        return NextResponse.json(
            { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
            { status: 500 }
        );
    }
}
