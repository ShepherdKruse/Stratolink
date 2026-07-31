import { NextRequest, NextResponse } from 'next/server';
import { canonicalDeviceId } from '@/lib/devices/aliases';
import { createServiceRoleClient } from '@/lib/supabase';
import { extractGateways, parseTTNPayload, type TTNWebhookPayload } from '@/lib/ttn/payload-parser';

/** fPorts that carry something other than primary telemetry. Their payloads
 *  must never be decoded as position telemetry — a wildlife detection parsed
 *  as lat/lon would insert a garbage row mid-flight. */
const WILDLIFE_F_PORT = 11;
const B2B_F_PORT = 12;

export async function POST(request: NextRequest) {
    try {
        const payload: TTNWebhookPayload = await request.json();

        /* Non-telemetry uplinks (wildlife/CTT on 11, balloon-to-balloon on 12,
         * anything else unknown) are stored raw and never parsed as telemetry.
         * fPort 1 — or a missing f_port, for backward compatibility with any
         * TTN config that omits it — falls through to the telemetry path. */
        const fPort = payload.uplink_message?.f_port;
        if (typeof fPort === 'number' && fPort !== 1) {
            return await storeUplinkEvent(payload, fPort);
        }

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

        const rawDeviceId = telemetry.device_id;
        telemetry.device_id = canonicalDeviceId(rawDeviceId);
        if (rawDeviceId !== telemetry.device_id) {
            console.log(`Telemetry alias ${rawDeviceId} → ${telemetry.device_id}`);
        }

        const hasGpsFix = telemetry.lat !== null && telemetry.lon !== null;

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

        const legacyRow = {
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
            gateways: telemetry.gateways,
        };
        const v2Row = {
            ...legacyRow,
            f_port: telemetry.f_port,
            frm_payload: telemetry.frm_payload,
            telemetry_version: telemetry.telemetry_version,
            status_byte: telemetry.status_byte,
            boot_count: telemetry.boot_count,
            power_tier: telemetry.power_tier,
            reset_cause: telemetry.reset_cause,
            gps_fix_age_min: telemetry.gps_fix_age_min,
            command_ack_seq: telemetry.command_ack_seq,
            relay_enabled: telemetry.relay_enabled,
            relay_fwd_delta: telemetry.relay_fwd_delta,
            ctt_tags_delta: telemetry.ctt_tags_delta,
        };

        let { error } = await supabase.from('telemetry').insert(v2Row);

        /* 42703 = undefined column: migration 010 hasn't run on this database
         * yet. Fall back to the legacy column set rather than dropping the
         * packet — losing flight telemetry over a deploy-order mismatch is
         * never the right trade. */
        if (error && error.code === '42703') {
            console.warn('telemetry v2 columns missing (migration 010 not applied) — inserting legacy columns only');
            ({ error } = await supabase.from('telemetry').insert(legacyRow));
        }

        if (error) {
            console.error('Supabase insert error:', error);
            return NextResponse.json(
                { error: 'Database insert failed', details: error.message },
                { status: 500 }
            );
        }

        if (hasGpsFix) {
            console.log(`Telemetry inserted for ${telemetry.device_id} at ${telemetry.lat}, ${telemetry.lon}`);
        } else {
            console.log(`Telemetry inserted for ${telemetry.device_id} (no GPS fix; sensor-only row)`);
        }

        return NextResponse.json({
            success: true,
            device_id: telemetry.device_id,
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

/** Store a non-telemetry uplink (wildlife fPort 11, B2B fPort 12, or anything
 *  unrecognised) raw in uplink_events. Always answers 200 once the payload is
 *  minimally valid — TTN shouldn't retry these, and losing a wildlife ping is
 *  preferable to TTN marking the webhook unhealthy mid-flight. */
async function storeUplinkEvent(payload: TTNWebhookPayload, fPort: number): Promise<NextResponse> {
    const deviceId = payload.end_device_ids?.device_id;
    if (!deviceId) {
        return NextResponse.json(
            { error: 'Invalid payload: missing required field device_id' },
            { status: 400 }
        );
    }

    const uplink = payload.uplink_message;
    const gateways = extractGateways(uplink?.rx_metadata);
    const strongest = gateways[0] ?? null;

    const supabase = createServiceRoleClient();
    const { error } = await supabase.from('uplink_events').insert({
        device_id: canonicalDeviceId(deviceId),
        time: payload.received_at || new Date().toISOString(),
        f_port: fPort,
        frm_payload: uplink?.frm_payload ?? null,
        rssi: strongest?.rssi ?? null,
        snr: strongest?.snr ?? null,
        gateways,
    });

    if (error) {
        /* 42P01 = table missing (migration 010 not applied). Log loudly but
         * don't 500 — the packet is also visible in TTN's console, and a
         * failing webhook must never jeopardise fPort-1 telemetry delivery. */
        console.error(`uplink_events insert failed for ${deviceId} fPort ${fPort}:`, error);
    } else {
        console.log(`Uplink event stored for ${deviceId} (fPort ${fPort})`);
    }

    return NextResponse.json({ success: true, device_id: canonicalDeviceId(deviceId), f_port: fPort }, { status: 200 });
}
