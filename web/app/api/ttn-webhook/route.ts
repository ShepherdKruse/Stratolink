import { NextRequest, NextResponse } from 'next/server';
import { createServiceRoleClient } from '@/lib/supabase';
import {
    parseB2BEventPayload,
    parseCTTEventPayload,
    parseTTNPayload,
    type TTNWebhookPayload,
} from '@/lib/ttn/payload-parser';
import {
    authorizeTTNWebhook,
    isExpectedTTNDeliveryDuplicate,
    isProvisionedFleetDevice,
    parseTTNUplinkIdentity,
    readRequestBodyWithinLimit,
} from '@/lib/ttn/webhook-auth';

const MAX_WEBHOOK_BODY_BYTES = 256 * 1024;

export async function POST(request: NextRequest) {
    const authorization = authorizeTTNWebhook(
        request.headers.get('authorization'),
        process.env.TTN_WEBHOOK_SECRET
    );
    if (!authorization.ok) {
        if (authorization.reason === 'misconfigured') {
            console.error('TTN webhook is disabled: TTN_WEBHOOK_SECRET is missing or too short');
            return NextResponse.json(
                { error: 'Webhook unavailable' },
                { status: 503 }
            );
        }
        return NextResponse.json(
            { error: 'Unauthorized' },
            {
                status: 401,
                headers: { 'WWW-Authenticate': 'Bearer' },
            }
        );
    }

    try {
        const contentLength = Number(request.headers.get('content-length'));
        if (Number.isFinite(contentLength) && contentLength > MAX_WEBHOOK_BODY_BYTES) {
            return NextResponse.json(
                { error: 'Webhook payload too large' },
                { status: 413 }
            );
        }

        const body = await readRequestBodyWithinLimit(request, MAX_WEBHOOK_BODY_BYTES);
        if (body === null) {
            return NextResponse.json(
                { error: 'Webhook payload too large' },
                { status: 413 }
            );
        }

        let payload: TTNWebhookPayload;
        try {
            payload = JSON.parse(body) as TTNWebhookPayload;
        } catch {
            return NextResponse.json(
                { error: 'Invalid JSON payload' },
                { status: 400 }
            );
        }

        const identity = parseTTNUplinkIdentity(payload);
        if (!identity) {
            return NextResponse.json(
                {
                    error:
                        'Invalid or missing TTN device/session identity, ' +
                        'server receive time, or frame counter',
                },
                { status: 400 }
            );
        }
        const fPort = payload.uplink_message?.f_port;
        if (fPort !== 1 && fPort !== 11 && fPort !== 12) {
            return NextResponse.json(
                { error: 'Unsupported or missing TTN fPort' },
                { status: 400 }
            );
        }
        const canonicalDeviceId = identity.rawDeviceId.replace(/-(eu|as|au)$/, '');

        // Every accepted uplink must belong to a provisioned fleet member.
        // Do this once before the fPort branches so auxiliary packets cannot
        // bypass the same identity gate as primary telemetry.
        const supabase = createServiceRoleClient();
        const { data: device, error: deviceError } = await supabase
            .from('devices')
            .select('device_id, status, claim_code')
            .eq('device_id', canonicalDeviceId)
            .maybeSingle();
        if (deviceError) {
            console.error('Device registry lookup failed:', deviceError);
            return NextResponse.json(
                { error: 'Device registry lookup failed' },
                { status: 500 }
            );
        }
        if (!device) {
            console.warn(
                `Rejected uplink from unregistered device ${canonicalDeviceId} ` +
                `(TTN ID: ${identity.rawDeviceId})`
            );
            return NextResponse.json(
                { error: 'Device is not registered' },
                { status: 404 }
            );
        }
        if (!isProvisionedFleetDevice(device)) {
            console.warn(
                `Rejected uplink from callsign reservation ${canonicalDeviceId} ` +
                `(TTN ID: ${identity.rawDeviceId})`
            );
            return NextResponse.json(
                { error: 'Device is reserved but not provisioned' },
                { status: 403 }
            );
        }

        /* Sparse wildlife detections use a typed fPort so the established
         * 35/40-byte primary telemetry wire contracts remain untouched. Route before
         * telemetry parsing: interpreting a 17-byte CTT event as lat/lon
         * would otherwise create a plausible-looking garbage row. */
        if (fPort === 11) {
            const event = parseCTTEventPayload(payload);
            if (!event) {
                return NextResponse.json(
                    { error: 'Invalid fPort-11 CTT event payload' },
                    { status: 400 }
                );
            }
            const { error } = await supabase
                .from('wildlife_detections')
                .insert({
                    device_id: canonicalDeviceId,
                    ttn_device_id: identity.rawDeviceId,
                    dev_addr: identity.devAddr,
                    session_key_id: identity.sessionKeyId,
                    ttn_received_at: identity.receivedAt,
                    f_cnt: identity.frameCounter,
                    time: event.time,
                    event_version: event.event_version,
                    detected_at: event.detected_at,
                    detection_age_min: event.detection_age_min,
                    raw_tag_id: event.raw_tag_id,
                    motus_tag_id: event.motus_tag_id,
                    motus_valid: event.motus_valid,
                    detection_rssi: event.detection_rssi,
                    hits: event.hits,
                    listen_window: event.listen_window,
                    link_rssi: event.link_rssi,
                    link_snr: event.link_snr,
                    lora_sf: event.lora_sf,
                    lora_bw: event.lora_bw,
                    frequency_hz: event.frequency_hz,
                });
            if (error) {
                if (isExpectedTTNDeliveryDuplicate(
                    error,
                    'idx_wildlife_detections_ttn_delivery'
                )) {
                    return NextResponse.json({
                        success: true,
                        duplicate: true,
                        event: 'ctt_detection',
                        device_id: canonicalDeviceId,
                    }, { status: 200 });
                }
                console.error('Wildlife detection insert error:', error);
                return NextResponse.json(
                    { error: 'Wildlife detection insert failed' },
                    { status: 500 }
                );
            }
            return NextResponse.json({
                success: true,
                event: 'ctt_detection',
                device_id: canonicalDeviceId,
                raw_tag_id: event.raw_tag_id,
            }, { status: 200 });
        }

        if (fPort === 12) {
            const event = parseB2BEventPayload(payload);
            if (!event) {
                return NextResponse.json(
                    { error: 'Invalid fPort-12 B2B frame' },
                    { status: 400 }
                );
            }
            const { error } = await supabase
                .from('b2b_packets')
                .insert({
                    gateway_balloon_id: canonicalDeviceId,
                    ttn_device_id: identity.rawDeviceId,
                    dev_addr: identity.devAddr,
                    session_key_id: identity.sessionKeyId,
                    ttn_received_at: identity.receivedAt,
                    f_cnt: identity.frameCounter,
                    time: event.time,
                    source_balloon_id: event.source_balloon_id,
                    message_id: event.message_id,
                    ttl: event.ttl,
                    frame_type: event.frame_type,
                    payload_base64: event.payload_base64,
                    raw_frame_base64: event.raw_frame_base64,
                    crumbs: event.crumbs,
                    command_target: event.command_target,
                    command_opcode: event.command_opcode,
                    command_seq: event.command_seq,
                    link_rssi: event.link_rssi,
                    link_snr: event.link_snr,
                    lora_sf: event.lora_sf,
                    lora_bw: event.lora_bw,
                    frequency_hz: event.frequency_hz,
                });
            if (error) {
                if (isExpectedTTNDeliveryDuplicate(
                    error,
                    'idx_b2b_packets_ttn_delivery'
                )) {
                    return NextResponse.json({
                        success: true,
                        duplicate: true,
                        event: 'b2b_packet',
                        gateway_balloon_id: canonicalDeviceId,
                    }, { status: 200 });
                }
                console.error('B2B packet insert error:', error);
                return NextResponse.json(
                    { error: 'B2B packet insert failed' },
                    { status: 500 }
                );
            }
            return NextResponse.json({
                success: true,
                event: 'b2b_packet',
                gateway_balloon_id: canonicalDeviceId,
                source_balloon_id: event.source_balloon_id,
                message_id: event.message_id,
            }, { status: 200 });
        }

        // Parse telemetry data from TTN webhook payload
        const telemetry = parseTTNPayload(payload);

        if (!telemetry) {
            console.error(
                `Failed to parse TTN payload from ${identity.rawDeviceId}, ` +
                `fCnt=${identity.frameCounter}, fPort=${payload.uplink_message?.f_port ?? 'missing'}`
            );
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
        if (device.status !== 'flying') {
            console.warn(
                `Telemetry received from device not in 'flying' status: ` +
                `${canonicalDeviceId} (status: ${device.status})`
            );
        }

        const { error } = await supabase
            .from('telemetry')
            .insert({
                device_id: canonicalDeviceId,
                ttn_device_id: identity.rawDeviceId,
                dev_addr: identity.devAddr,
                session_key_id: identity.sessionKeyId,
                ttn_received_at: identity.receivedAt,
                f_cnt: identity.frameCounter,
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
                telemetry_version: telemetry.telemetry_version,
                power_tier: telemetry.power_tier,
                reset_cause: telemetry.reset_cause,
                boot_count: telemetry.boot_count,
                gps_fix_age_min: telemetry.gps_fix_age_min,
                command_ack_seq: telemetry.command_ack_seq,
                relay_enabled: telemetry.relay_enabled,
                relay_fwd_delta: telemetry.relay_fwd_delta,
                ctt_tags_delta: telemetry.ctt_tags_delta,
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
            if (isExpectedTTNDeliveryDuplicate(
                error,
                'idx_telemetry_ttn_delivery'
            )) {
                return NextResponse.json({
                    success: true,
                    duplicate: true,
                    device_id: canonicalDeviceId,
                    ttn_device_id: identity.rawDeviceId,
                    f_cnt: identity.frameCounter,
                }, { status: 200 });
            }
            console.error('Supabase insert error:', error);
            return NextResponse.json(
                { error: 'Database insert failed' },
                { status: 500 }
            );
        }

        if (hasGpsFix) {
            console.log(`Telemetry inserted for ${canonicalDeviceId} (TTN: ${telemetry.device_id}) at ${telemetry.lat}, ${telemetry.lon}`);
        } else {
            console.log(`Telemetry inserted for ${canonicalDeviceId} (TTN: ${telemetry.device_id}; no GPS fix, sensor-only row)`);
        }

        return NextResponse.json({
            success: true,
            device_id: canonicalDeviceId,
            ttn_device_id: telemetry.device_id,
            gps_fix: hasGpsFix,
        }, { status: 200 });

    } catch (error) {
        console.error('Webhook processing error:', error);
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
