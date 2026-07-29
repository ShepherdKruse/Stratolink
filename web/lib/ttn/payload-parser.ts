/**
 * TTN Payload Parser
 * 
 * Handles parsing of telemetry data from The Things Network webhook payloads.
 * Supports both JSON (via TTN Payload Formatter) and binary formats.
 */

export interface TelemetryData {
    device_id: string;
    time: string;
    /** Latitude in degrees. null when firmware reports no GPS fix (NOGPS power tier). */
    lat: number | null;
    /** Longitude in degrees. null when firmware reports no GPS fix (NOGPS power tier). */
    lon: number | null;
    /** Altitude in meters. null when firmware reports no GPS fix. */
    altitude_m: number | null;
    velocity_x?: number | null;
    velocity_y?: number | null;
    temperature?: number | null;
    pressure?: number | null;
    solar_voltage?: number | null;
    battery_voltage?: number | null;
    rssi?: number | null;
    snr?: number | null;
    gps_speed?: number | null;
    gps_heading?: number | null;
    gps_satellites?: number | null;
    mems_accel_x?: number | null;
    mems_accel_y?: number | null;
    mems_accel_z?: number | null;
    /** LTR-390UV-01: integer UV index (0-15+) */
    uv_index?: number | null;
    /** LTR-390UV-01: ambient light in lux */
    ambient_lux?: number | null;
    /** 0 = quiet, 1 = acoustic event, null = capture skipped/failed */
    acoustic_event?: number | null;

    /** Length-gated binary telemetry contract (1 = 35 bytes, 2 = 40 bytes). */
    telemetry_version?: number | null;
    /** Firmware load-shedding tier: 0 FULL through 4 CRITICAL. */
    power_tier?: number | null;
    /** Compact reset-cause code: 0 unknown, 1 watchdog, 2 software,
     * 3 low-power/option, 4 cold power-on, 5 warm brownout, 6 NRST. */
    reset_cause?: number | null;
    boot_count?: number | null;
    /** Minutes since a fresh accepted GNSS fix; null means none this boot. */
    gps_fix_age_min?: number | null;
    /** Last durably applied fPort-10 application sequence. */
    command_ack_seq?: number | null;
    relay_enabled?: boolean | null;
    relay_fwd_delta?: number | null;
    ctt_tags_delta?: number | null;

    /* Optional legacy/formatter-only system state. The exact binary v2 health
     * contract above is decoded directly from its 40-byte FRMPayload. */
    firmware_version?: string | null;
    uptime_s?: number | null;
    tx_count?: number | null;
    hdop?: number | null;
    power_mode?: string | null;
    sleep_ms?: number | null;

    /* LoRa link characteristics, sourced from TTN rx settings rather than
     * the device payload. These are always known per-uplink. */
    lora_sf?: number | null;
    lora_bw?: number | null;
    frequency_hz?: number | null;
}

export interface CTTEventData {
    device_id: string;
    time: string;
    event_version: number;
    detected_at: string | null;
    detection_age_min: number | null;
    raw_tag_id: number;
    motus_tag_id: number | null;
    motus_valid: boolean;
    detection_rssi: number;
    hits: number;
    listen_window: number | null;
    link_rssi: number | null;
    link_snr: number | null;
    lora_sf: number | null;
    lora_bw: number | null;
    frequency_hz: number | null;
}

export interface B2BEventData {
    device_id: string;
    time: string;
    source_balloon_id: number;
    message_id: number;
    ttl: number;
    frame_type: 'crumb' | 'command' | 'ack';
    payload_base64: string;
    raw_frame_base64: string;
    crumbs: Array<{ lat: number; lon: number; altitude_m: number; age_min: number }> | null;
    command_target: number | null;
    command_opcode: number | null;
    command_seq: number | null;
    link_rssi: number | null;
    link_snr: number | null;
    lora_sf: number | null;
    lora_bw: number | null;
    frequency_hz: number | null;
}

export interface TTNWebhookPayload {
    end_device_ids?: {
        device_id?: string;
        /** LoRaWAN DevAddr, used when a manually provisioned session has no session_key_id. */
        dev_addr?: string;
    };
    received_at?: string;
    uplink_message?: {
        f_port?: number;
        /** TTN session identifier; absent on the current StratoLink manual session. */
        session_key_id?: string;
        /** LoRaWAN uplink frame counter, stored with TTN's server receive time. */
        f_cnt?: number;
        frm_payload?: string; // Base64 encoded binary
        decoded_payload?: Record<string, any>; // JSON if using TTN formatter
        rx_metadata?: Array<{
            rssi?: number;
            snr?: number;
        }>;
        /* TTN's per-uplink radio settings. Shape per LoRaWAN stack v3:
         * settings.data_rate.lora.{spreading_factor,bandwidth,coding_rate}
         * settings.frequency = carrier frequency in Hz (string). */
        settings?: {
            data_rate?: {
                lora?: {
                    spreading_factor?: number;
                    bandwidth?: number;
                };
            };
            frequency?: string | number;
        };
    };
}

/**
 * Parse the dedicated fPort-11 CTT wildlife-event wire contract.
 * Exact length, magic, version, and reserved flags are all checked so a
 * telemetry packet routed to the wrong fPort cannot become a plausible tag.
 */
export function parseCTTEventPayload(payload: TTNWebhookPayload): CTTEventData | null {
    const deviceId = payload.end_device_ids?.device_id;
    const receivedAt = payload.received_at || new Date().toISOString();
    const uplink = payload.uplink_message;
    if (!deviceId || !uplink || uplink.f_port !== 11 || !uplink.frm_payload) return null;

    try {
        const buffer = Buffer.from(uplink.frm_payload, 'base64');
        const version = buffer[2];
        if (buffer.length !== 17 ||
            buffer[0] !== 0x43 || buffer[1] !== 0x54 ||
            (version !== 1 && version !== 2) || (buffer[3] & 0xFE) !== 0) {
            return null;
        }
        const motusValid = (buffer[3] & 0x01) !== 0;
        const motusId = buffer.readUInt32BE(8);
        const hits = buffer.readUInt8(14);
        if ((!motusValid && motusId !== 0) ||
            (motusValid && motusId > 0xFFFFF) || hits === 0) {
            return null;
        }
        const finalField = buffer.readUInt16BE(15);
        const receivedMs = Date.parse(receivedAt);
        if (version === 2 && !Number.isFinite(receivedMs)) return null;
        const detectedAt = version === 2
            ? new Date(receivedMs - finalField * 60_000).toISOString()
            : null;
        const rx = uplink.rx_metadata?.[0];
        return {
            device_id: deviceId,
            time: detectedAt ?? receivedAt,
            event_version: version,
            detected_at: detectedAt,
            detection_age_min: version === 2 ? finalField : null,
            raw_tag_id: buffer.readUInt32BE(4),
            motus_tag_id: motusValid ? motusId : null,
            motus_valid: motusValid,
            detection_rssi: buffer.readInt16BE(12),
            hits,
            listen_window: version === 1 ? finalField : null,
            link_rssi: typeof rx?.rssi === 'number' ? rx.rssi : null,
            link_snr: typeof rx?.snr === 'number' ? rx.snr : null,
            ...extractLoraSettings(uplink),
        };
    } catch (error) {
        console.error('Error parsing CTT event payload:', error);
        return null;
    }
}

/**
 * Parse a complete version-3 StratoLink B2B frame tunneled on fPort 12.
 *
 * The receiving balloon has already verified the fleet AES-CMAC before it
 * places this exact frame on its authenticated LoRaWAN uplink. The web tier
 * deliberately treats the final eight bytes as an opaque transport tag: it
 * validates the v3 envelope and type-specific body shape, but never mistakes
 * tag bytes for crumbs or command arguments.
 */
export function parseB2BEventPayload(payload: TTNWebhookPayload): B2BEventData | null {
    const deviceId = payload.end_device_ids?.device_id;
    const receivedAt = payload.received_at || new Date().toISOString();
    const uplink = payload.uplink_message;
    if (!deviceId || !uplink || uplink.f_port !== 12 || !uplink.frm_payload) return null;

    try {
        const frame = Buffer.from(uplink.frm_payload, 'base64');
        if (frame.length < 9 ||
            frame[0] !== 0x53 || frame[1] !== 0x42 || frame[2] !== 3 ||
            frame.readUInt16BE(3) === 0xFFFF ||
            frame[6] > 3 || (frame[7] & 0xFC) !== 0) return null;
        const payloadLength = frame[8];
        /* US915 DR1 caps the application payload at 53 bytes. The B2B header
         * consumes 9, so wire-v3 payloads above 44 can never be emitted by a
         * conforming flight image and fail closed here too. */
        if (payloadLength > 44 || frame.length !== 9 + payloadLength) return null;
        const type = frame[7] & 0x03;
        const authTagLength = 8;
        if (payloadLength < authTagLength) return null;
        const authenticatedPayload = frame.subarray(9);
        const body = authenticatedPayload.subarray(
            0, authenticatedPayload.length - authTagLength);
        const shapeOk =
            (type === 0 && body.length > 0 && body.length % 6 === 0) ||
            (type === 1 && body.length >= 4) ||
            (type === 2 && body.length === 3);
        if (!shapeOk) return null;

        let crumbs: B2BEventData['crumbs'] = null;
        if (type === 0) {
            crumbs = [];
            for (let offset = 0; offset < body.length; offset += 6) {
                const latCd = body.readInt16BE(offset);
                const lonCd = body.readInt16BE(offset + 2);
                /* Authentication does not make corrupt-but-authentic sensor
                 * state physically possible. Keep semantic range checks as a
                 * second, independent ingestion boundary. */
                if (latCd < -9000 || latCd > 9000 ||
                    lonCd < -18000 || lonCd > 18000) return null;
                crumbs.push({
                    lat: latCd / 100,
                    lon: lonCd / 100,
                    altitude_m: body.readUInt8(offset + 4) * 100,
                    age_min: body.readUInt8(offset + 5),
                });
            }
        }
        const rx = uplink.rx_metadata?.[0];
        return {
            device_id: deviceId,
            time: receivedAt,
            source_balloon_id: frame.readUInt16BE(3),
            message_id: frame.readUInt8(5),
            ttl: frame.readUInt8(6),
            frame_type: type === 0 ? 'crumb' : type === 1 ? 'command' : 'ack',
            payload_base64: body.toString('base64'),
            raw_frame_base64: frame.toString('base64'),
            crumbs,
            command_target: type === 1 || type === 2 ? body.readUInt16BE(0) : null,
            command_opcode: type === 1 ? body.readUInt8(2) : null,
            command_seq: type === 1 ? body.readUInt8(3)
                : type === 2 ? body.readUInt8(2) : null,
            link_rssi: typeof rx?.rssi === 'number' ? rx.rssi : null,
            link_snr: typeof rx?.snr === 'number' ? rx.snr : null,
            ...extractLoraSettings(uplink),
        };
    } catch (error) {
        console.error('Error parsing B2B event payload:', error);
        return null;
    }
}

/** Pull LoRa SF / bandwidth / carrier frequency out of a TTN uplink. */
function extractLoraSettings(uplink: TTNWebhookPayload['uplink_message']): {
    lora_sf: number | null;
    lora_bw: number | null;
    frequency_hz: number | null;
} {
    const exactInteger = (value: unknown): number | null => {
        if (typeof value === 'number') {
            return Number.isSafeInteger(value) ? value : null;
        }
        if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) {
            return null;
        }
        const parsed = Number(value);
        return Number.isSafeInteger(parsed) ? parsed : null;
    };
    const settings = uplink?.settings;
    const lora = settings?.data_rate?.lora;
    const sf = exactInteger(lora?.spreading_factor);
    const bandwidth = exactInteger(lora?.bandwidth);
    const frequency = exactInteger(settings?.frequency);
    return {
        lora_sf: sf !== null && sf >= 5 && sf <= 12 ? sf : null,
        lora_bw: bandwidth !== null && bandwidth >= 7_800 && bandwidth <= 500_000
            ? bandwidth : null,
        frequency_hz: frequency !== null &&
            frequency >= 100_000_000 && frequency <= 1_000_000_000
            ? frequency : null,
    };
}

/**
 * Parse telemetry from TTN webhook payload
 * Supports both JSON (decoded_payload) and binary (frm_payload) formats
 */
export function parseTTNPayload(payload: TTNWebhookPayload): TelemetryData | null {
    const deviceId = payload.end_device_ids?.device_id;
    const receivedAt = payload.received_at || new Date().toISOString();
    const uplinkMessage = payload.uplink_message;

    if (!deviceId || !uplinkMessage) {
        return null;
    }

    const loraSettings = extractLoraSettings(uplinkMessage);

    /* The signed LoRaWAN FRMPayload is authoritative. A TTN formatter can lag
     * a firmware rollout and emit a plausible but incomplete decoded_payload;
     * preferring that JSON would silently discard v2 reset/GNSS/command state.
     * Decode exact-length primary wire contracts first whenever raw bytes are
     * present, then support JSON-only integrations as a compatibility path. */
    if (uplinkMessage.frm_payload) {
        const parsed = parseBinaryPayload(deviceId, receivedAt, uplinkMessage.frm_payload, uplinkMessage.rx_metadata);
        return parsed ? { ...parsed, ...loraSettings } : null;
    }

    if (uplinkMessage.decoded_payload) {
        const parsed = parseJSONPayload(deviceId, receivedAt, uplinkMessage.decoded_payload, uplinkMessage.rx_metadata);
        return parsed ? { ...parsed, ...loraSettings } : null;
    }

    return null;
}

/**
 * Parse JSON payload from TTN Payload Formatter
 */
function parseJSONPayload(
    deviceId: string,
    receivedAt: string,
    decoded: Record<string, any>,
    rxMetadata?: Array<{ rssi?: number; snr?: number }>
): TelemetryData | null {
    // Extract receiver characteristics from rx_metadata (first gateway)
    const rxData = rxMetadata && rxMetadata.length > 0 ? rxMetadata[0] : null;

    const rawNumber = (...keys: string[]): number | null => {
        for (const key of keys) {
            if (decoded[key] === undefined || decoded[key] === null ||
                decoded[key] === '') continue;
            /* Number.parseFloat("12garbage") returns 12. A JSON-only TTN
             * formatter is already the weaker compatibility boundary, so do
             * not also accept a numeric prefix from malformed/stale output. */
            const text = String(decoded[key]).trim();
            if (text === '') continue;
            const value = Number(text);
            if (Number.isFinite(value)) return value;
        }
        return null;
    };
    const numOr = rawNumber;
    const rawLatValue = rawNumber('latitude', 'lat');
    const rawLonValue = rawNumber('longitude', 'lon');
    const rawAltValue = rawNumber('altitude', 'altitude_m');
    const rawLat = rawLatValue ?? 0;
    const rawLon = rawLonValue ?? 0;
    const rawAlt = rawAltValue ?? 0;
    const reportedSats = rawNumber('gps_satellites', 'gps_sats', 'sats');
    const reportedSpeed = rawNumber('gps_speed', 'ground_spd', 'speed');
    const reportedHeading = rawNumber('gps_heading', 'heading');
    const reportedVelocityX = rawNumber('velocity_x');
    const reportedVelocityY = rawNumber('velocity_y');
    /* Apply the same atomic two-state contract as the signed binary payload.
     * The JSON-only path exists for compatibility, but it must not turn a
     * stale formatter into a second, weaker GNSS trust boundary. */
    const validLat = Number.isFinite(rawLat) && rawLat >= -90 && rawLat <= 90;
    const validLon = Number.isFinite(rawLon) && rawLon >= -180 && rawLon <= 180;
    /* Missing fields are not the firmware's explicit zero sentinel. Keeping
     * this shape bit separate prevents an empty decoded_payload—or a
     * formatter that dropped one position field—from becoming a nominal
     * NOGPS row after the null-to-zero defaults above. */
    const positionShapeComplete = rawLatValue !== null &&
        rawLonValue !== null && rawAltValue !== null;
    const allZeroSentinel = positionShapeComplete &&
        rawLat === 0 && rawLon === 0 && rawAlt === 0;
    const explicitFix = typeof decoded.gps_fix === 'boolean'
        ? decoded.gps_fix : null;
    const fixClaimed = (
        explicitFix !== null ? explicitFix :
        reportedSats !== null ? reportedSats >= 4 :
        !allZeroSentinel
    );
    const motionPairShape =
        (reportedVelocityX === null && reportedVelocityY === null) ||
        (reportedVelocityX !== null && reportedVelocityY !== null &&
         Math.abs(reportedVelocityX) <= 500 &&
         Math.abs(reportedVelocityY) <= 500);
    const validGpsFix = fixClaimed && positionShapeComplete &&
        validLat && validLon &&
        rawAlt >= -500 && rawAlt <= 60000 &&
        reportedSats !== null && Number.isInteger(reportedSats) &&
        reportedSats >= 4 && reportedSats <= 64 &&
        reportedSpeed !== null && reportedSpeed >= 0 && reportedSpeed <= 500 &&
        reportedHeading !== null && reportedHeading >= 0 && reportedHeading < 360 &&
        motionPairShape;
    const noGpsSentinel = !fixClaimed && allZeroSentinel &&
        reportedSats === 0 && reportedSpeed === 0 && reportedHeading === 0 &&
        (reportedVelocityX === null || reportedVelocityX === 0) &&
        (reportedVelocityY === null || reportedVelocityY === 0);
    if (!validGpsFix && !noGpsSentinel) return null;
    const hasGpsFix = validGpsFix;

    /* Number / string coercion helpers that preserve null for missing keys
     * but accept either canonical name or a few common aliases the firmware
     * payload formatter may use. */
    const intOr = (...keys: string[]): number | null => {
        const n = numOr(...keys);
        return n === null ? null : Math.trunc(n);
    };
    const strOr = (...keys: string[]): string | null => {
        for (const k of keys) {
            if (decoded[k] !== undefined && decoded[k] !== null && decoded[k] !== '') {
                return String(decoded[k]);
            }
        }
        return null;
    };

    return {
        device_id: deviceId,
        time: receivedAt,
        lat: hasGpsFix ? rawLat : null,
        lon: hasGpsFix ? rawLon : null,
        altitude_m: hasGpsFix ? rawAlt : null,
        /* A formatter can retain motion fields after it has already declared
         * NOGPS. Keep every position-derived value atomic with the accepted
         * fix instead of storing a null location beside cached motion. */
        velocity_x: hasGpsFix
            ? reportedVelocityX ?? reportedSpeed! * Math.sin(reportedHeading! * Math.PI / 180)
            : null,
        velocity_y: hasGpsFix
            ? reportedVelocityY ?? reportedSpeed! * Math.cos(reportedHeading! * Math.PI / 180)
            : null,
        temperature: numOr('temperature', 'temp_c'),
        pressure: numOr('pressure', 'pressure_hpa', 'pressure_mbar'),
        solar_voltage: (() => {
            const v = numOr('solar_voltage', 'solar_v');
            if (v !== null) return v;
            const mv = numOr('solar_mv');
            return mv === null ? null : mv / 1000;
        })(),
        battery_voltage: (() => {
            const v = numOr('battery_voltage', 'battery_v', 'vbat');
            if (v !== null) return v;
            const mv = numOr('battery_mv', 'vbat_mv');
            return mv === null ? null : mv / 1000;
        })(),
        rssi: rxData?.rssi !== undefined ? parseFloat(String(rxData.rssi)) : numOr('rssi'),
        snr: rxData?.snr !== undefined ? parseFloat(String(rxData.snr)) : numOr('snr'),
        gps_speed: hasGpsFix ? reportedSpeed : null,
        gps_heading: hasGpsFix ? reportedHeading : null,
        gps_satellites: hasGpsFix
            ? Math.trunc(reportedSats!)
            : reportedSats === 0 ? 0 : null,
        mems_accel_x: numOr('mems_accel_x', 'accel_x'),
        mems_accel_y: numOr('mems_accel_y', 'accel_y'),
        mems_accel_z: numOr('mems_accel_z', 'accel_z'),
        uv_index: intOr('uv_index'),
        ambient_lux: numOr('ambient_lux', 'lux'),
        acoustic_event: intOr('acoustic_event', 'acoustic'),
        telemetry_version: intOr('telemetry_version'),
        power_tier: intOr('power_tier'),
        reset_cause: intOr('reset_cause'),
        boot_count: intOr('boot_count'),
        gps_fix_age_min: intOr('gps_fix_age_min', 'fix_age_min'),
        command_ack_seq: intOr('command_ack_seq'),
        relay_enabled: typeof decoded.relay_enabled === 'boolean'
            ? decoded.relay_enabled : null,
        relay_fwd_delta: intOr('relay_fwd_delta'),
        ctt_tags_delta: intOr('ctt_tags_delta'),
        firmware_version: strOr('firmware_version', 'firmware', 'fw'),
        uptime_s: intOr('uptime_s', 'uptime'),
        tx_count: intOr('tx_count', 'tx'),
        hdop: numOr('hdop'),
        power_mode: strOr('power_mode', 'power'),
        sleep_ms: intOr('sleep_ms', 'sleep'),
    };
}

/**
 * Parse binary payload (if firmware sends raw bytes)
 * 
 * 35-byte v1 or 40-byte v2 big-endian payload (matches telemetry_pack):
 * Byte 0-3:   Latitude (int32, degrees * 1e7)
 * Byte 4-7:   Longitude (int32, degrees * 1e7)
 * Byte 8-11:  Altitude in meters (int32)
 * Byte 12-13: Temperature in 0.1 C (int16; -32768 = unavailable)
 * Byte 14-15: Pressure in 0.1 hPa (uint16; 0xFFFE = unavailable)
 * Byte 16-17: Solar voltage in mV (uint16)
 * Byte 18-19: Battery voltage in mV (uint16)
 * Byte 20-21: GPS speed in 0.01 m/s (uint16)
 * Byte 22-23: GPS heading in 0.01 deg (uint16)
 * Byte 24:    GPS satellites (uint8)
 * Byte 25-26: Accel X in 0.01 m/s2 (int16; -32768 = unavailable)
 * Byte 27-28: Accel Y in 0.01 m/s2 (int16; -32768 = unavailable)
 * Byte 29-30: Accel Z in 0.01 m/s2 (int16; -32768 = unavailable)
 * Byte 31:    UV index (uint8, 0-15+; 0xFE = unavailable)
 * Byte 32-33: Ambient lux (uint16; 0xFFFE = unavailable)
 * Byte 34 v1: Acoustic event (uint8, 0=quiet, 1=event)
 * Byte 34 v2: lower code 0-9 = power*2+acoustic, 10-14 = acoustic
 * unavailable at power 0-4, 15 invalid; reset cause[6:4], cmd-valid[7]
 * Byte 35 v2: retained boot count, low byte
 * Byte 36-37: minutes since fresh GNSS fix (0xFFFF = none this boot)
 * Byte 38:    last applied command sequence (meaningful when cmd-valid)
 * Byte 39:    relay-enabled[7], relay-forward delta[6:4], CTT delta[3:0]
 */
function parseBinaryPayload(
    deviceId: string,
    receivedAt: string,
    frmPayload: string,
    rxMetadata?: Array<{ rssi?: number; snr?: number }>
): TelemetryData | null {
    try {
        const buffer = Buffer.from(frmPayload, 'base64');
        
        // Both contracts are exact. Accepting a prefix or intermediate length
        // would turn a truncated payload into a plausible row and, worse,
        // could reinterpret the v2 status byte as an acoustic count.
        if (buffer.length !== 35 && buffer.length !== 40) {
            console.error('Binary telemetry payload has invalid length:', buffer.length);
            return null;
        }

        const rawLat = buffer.readInt32BE(0) / 1e7;
        const rawLon = buffer.readInt32BE(4) / 1e7;
        const rawAlt = buffer.readInt32BE(8);
        const gps_satellites = buffer.readUInt8(24);
        const rawSpeedCmS = buffer.readUInt16BE(20);
        const rawHeadingCdeg = buffer.readUInt16BE(22);

        /* NOGPS power tier sentinel: firmware writes 0/0/0 when there's no fix.
         * Treat that as "no GPS data" rather than coordinates at Null Island.
         * Also reject physically impossible coordinates from a bit-flipped or
         * misaligned packet — observed e.g. lat=-208 in production. Latitude
         * or longitude zero alone is valid (equator / prime meridian), and
         * even 0/0/0 is distinguishable from NOGPS in both wire versions
         * because a firmware-approved fix carries >=4 satellites. */
        const validLat = Number.isFinite(rawLat) && rawLat >= -90 && rawLat <= 90;
        const validLon = Number.isFinite(rawLon) && rawLon >= -180 && rawLon <= 180;
        const noGpsSentinel = gps_satellites === 0 && rawLat === 0 &&
            rawLon === 0 && rawAlt === 0 && rawSpeedCmS === 0 &&
            rawHeadingCdeg === 0;
        const validGpsFix = gps_satellites >= 4 && gps_satellites <= 64 &&
            validLat && validLon && rawAlt >= -500 && rawAlt <= 60000 &&
            rawSpeedCmS <= 50000 && rawHeadingCdeg <= 35999;
        /* The flight encoder has exactly two GPS states: an all-zero NOGPS
         * sentinel, or a value-gated fresh PVT with 4..64 satellites. Do not
         * persist mixed states such as 1..3 satellites plus cached nonzero
         * coordinates; those are neither an honest no-fix packet nor a
         * firmware-approved fix and recreate the ambiguity seen in Flight 3. */
        if (!noGpsSentinel && !validGpsFix) return null;
        const hasGpsFix = validGpsFix;
        if ((rawLat !== 0 || rawLon !== 0) && (!validLat || !validLon)) {
            console.warn(`Dropping out-of-range GPS coords from ${deviceId}: lat=${rawLat} lon=${rawLon}`);
        }
        const lat = hasGpsFix ? rawLat : null;
        const lon = hasGpsFix ? rawLon : null;
        const altitude_m = hasGpsFix ? rawAlt : null;

        // Extract receiver characteristics
        const rxData = rxMetadata && rxMetadata.length > 0 ? rxMetadata[0] : null;

        // Parse optional fields if available
        const rawTemperature = buffer.readInt16BE(12);
        const rawPressure = buffer.readUInt16BE(14);
        const temperature = rawTemperature === -32768
            ? null : rawTemperature / 10;
        const pressure = rawPressure === 0xFFFE ? null : rawPressure / 10;
        const solar_voltage = buffer.length >= 18 ? buffer.readUInt16BE(16) / 1000 : null;
        const battery_voltage = buffer.length >= 20 ? buffer.readUInt16BE(18) / 1000 : null;
        const gps_speed = hasGpsFix ? rawSpeedCmS / 100 : null;
        const gps_heading = hasGpsFix ? rawHeadingCdeg / 100 : null;
        const rawAccel = [
            buffer.readInt16BE(25),
            buffer.readInt16BE(27),
            buffer.readInt16BE(29),
        ];
        const unavailableAccelAxes = rawAccel.filter(value => value === -32768).length;
        /* Firmware commits XYZ atomically. A mixed sentinel is packet
         * corruption or a contract violation, not a partially usable sample. */
        if (unavailableAccelAxes !== 0 && unavailableAccelAxes !== 3) return null;
        const accelAvailable = unavailableAccelAxes === 0;
        const mems_accel_x = accelAvailable ? rawAccel[0] / 100 : null;
        const mems_accel_y = accelAvailable ? rawAccel[1] / 100 : null;
        const mems_accel_z = accelAvailable ? rawAccel[2] / 100 : null;
        const rawUv = buffer.readUInt8(31);
        const rawLux = buffer.readUInt16BE(32);
        const uv_index = rawUv === 0xFE ? null : rawUv;
        const ambient_lux = rawLux === 0xFFFE ? null : rawLux;
        const telemetry_version = buffer.length === 40 ? 2 : 1;
        const status = buffer.readUInt8(34);
        const acousticPowerCode = status & 0x0F;
        const powerTier = acousticPowerCode <= 9
            ? acousticPowerCode >> 1
            : acousticPowerCode <= 14 ? acousticPowerCode - 10 : null;
        if ((telemetry_version === 1 && status > 1) ||
            (telemetry_version === 2 && powerTier === null) ||
            (telemetry_version === 2 && ((status >> 4) & 0x07) > 6)) {
            return null;
        }
        const acoustic_event = telemetry_version === 2
            ? (acousticPowerCode <= 9 ? acousticPowerCode & 0x01 : null)
            : status;
        const commandValid = telemetry_version === 2 && (status & 0x80) !== 0;
        const fixAgeWire = telemetry_version === 2 ? buffer.readUInt16BE(36) : null;
        const activity = telemetry_version === 2 ? buffer.readUInt8(39) : 0;

        // Calculate velocity from GPS if available
        let velocity_x = null;
        let velocity_y = null;
        if (gps_speed !== null && gps_heading !== null) {
            const headingRad = (gps_heading * Math.PI) / 180;
            velocity_x = gps_speed * Math.sin(headingRad);
            velocity_y = gps_speed * Math.cos(headingRad);
        }

        return {
            device_id: deviceId,
            time: receivedAt,
            lat,
            lon,
            altitude_m,
            velocity_x,
            velocity_y,
            temperature,
            pressure,
            solar_voltage,
            battery_voltage,
            rssi: rxData?.rssi !== undefined ? parseFloat(String(rxData.rssi)) : null,
            snr: rxData?.snr !== undefined ? parseFloat(String(rxData.snr)) : null,
            gps_speed,
            gps_heading,
            gps_satellites,
            mems_accel_x,
            mems_accel_y,
            mems_accel_z,
            uv_index,
            ambient_lux,
            acoustic_event,
            telemetry_version,
            power_tier: telemetry_version === 2 ? powerTier : null,
            reset_cause: telemetry_version === 2 ? (status >> 4) & 0x07 : null,
            boot_count: telemetry_version === 2 ? buffer.readUInt8(35) : null,
            gps_fix_age_min: fixAgeWire === 0xFFFF ? null : fixAgeWire,
            command_ack_seq: commandValid ? buffer.readUInt8(38) : null,
            relay_enabled: telemetry_version === 2
                ? (activity & 0x80) !== 0 : null,
            relay_fwd_delta: telemetry_version === 2
                ? (activity >> 4) & 0x07 : null,
            ctt_tags_delta: telemetry_version === 2 ? activity & 0x0F : null,
        };
    } catch (error) {
        console.error('Error parsing binary payload:', error);
        return null;
    }
}
