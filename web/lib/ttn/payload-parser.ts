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
    /** 0 = quiet, 1 = acoustic event detected (mic RMS > 4x noise floor) */
    acoustic_event?: number | null;

    /* Firmware-reported system state. Only populated when the device sends a
     * JSON payload via the TTN Payload Formatter that includes these keys.
     * The current 35-byte binary format does not carry them. */
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

export interface TTNWebhookPayload {
    end_device_ids?: {
        device_id?: string;
    };
    received_at?: string;
    uplink_message?: {
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

/** Pull LoRa SF / bandwidth / carrier frequency out of a TTN uplink. */
function extractLoraSettings(uplink: TTNWebhookPayload['uplink_message']): {
    lora_sf: number | null;
    lora_bw: number | null;
    frequency_hz: number | null;
} {
    const settings = uplink?.settings;
    const lora = settings?.data_rate?.lora;
    const freqRaw = settings?.frequency;
    const freq = freqRaw === undefined ? null
        : typeof freqRaw === 'string' ? parseInt(freqRaw, 10)
        : freqRaw;
    return {
        lora_sf: typeof lora?.spreading_factor === 'number' ? lora.spreading_factor : null,
        lora_bw: typeof lora?.bandwidth === 'number' ? lora.bandwidth : null,
        frequency_hz: typeof freq === 'number' && Number.isFinite(freq) ? freq : null,
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

    // Try JSON format first (TTN Payload Formatter)
    if (uplinkMessage.decoded_payload) {
        const parsed = parseJSONPayload(deviceId, receivedAt, uplinkMessage.decoded_payload, uplinkMessage.rx_metadata);
        return { ...parsed, ...loraSettings };
    }

    // Fall back to binary format
    if (uplinkMessage.frm_payload) {
        const parsed = parseBinaryPayload(deviceId, receivedAt, uplinkMessage.frm_payload, uplinkMessage.rx_metadata);
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
): TelemetryData {
    // Extract receiver characteristics from rx_metadata (first gateway)
    const rxData = rxMetadata && rxMetadata.length > 0 ? rxMetadata[0] : null;

    const rawLat = parseFloat(decoded.latitude) || parseFloat(decoded.lat) || 0;
    const rawLon = parseFloat(decoded.longitude) || parseFloat(decoded.lon) || 0;
    const rawAlt = parseFloat(decoded.altitude) || parseFloat(decoded.altitude_m) || 0;
    const hasGpsFix = rawLat !== 0 && rawLon !== 0;

    /* Number / string coercion helpers that preserve null for missing keys
     * but accept either canonical name or a few common aliases the firmware
     * payload formatter may use. */
    const numOr = (...keys: string[]): number | null => {
        for (const k of keys) {
            if (decoded[k] !== undefined && decoded[k] !== null && decoded[k] !== '') {
                const n = parseFloat(String(decoded[k]));
                if (Number.isFinite(n)) return n;
            }
        }
        return null;
    };
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
        velocity_x: numOr('velocity_x'),
        velocity_y: numOr('velocity_y'),
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
        gps_speed: numOr('gps_speed', 'ground_spd', 'speed'),
        gps_heading: numOr('gps_heading', 'heading'),
        gps_satellites: intOr('gps_satellites', 'gps_sats', 'sats'),
        mems_accel_x: numOr('mems_accel_x', 'accel_x'),
        mems_accel_y: numOr('mems_accel_y', 'accel_y'),
        mems_accel_z: numOr('mems_accel_z', 'accel_z'),
        uv_index: intOr('uv_index'),
        ambient_lux: numOr('ambient_lux', 'lux'),
        acoustic_event: intOr('acoustic_event', 'acoustic'),
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
 * 35-byte big-endian payload (matches firmware telemetry_pack):
 * Byte 0-3:   Latitude (int32, degrees * 1e7)
 * Byte 4-7:   Longitude (int32, degrees * 1e7)
 * Byte 8-11:  Altitude in meters (int32)
 * Byte 12-13: Temperature in 0.1 C (int16)
 * Byte 14-15: Pressure in 0.1 hPa (uint16)
 * Byte 16-17: Solar voltage in mV (uint16)
 * Byte 18-19: Battery voltage in mV (uint16)
 * Byte 20-21: GPS speed in 0.01 m/s (uint16)
 * Byte 22-23: GPS heading in 0.01 deg (uint16)
 * Byte 24:    GPS satellites (uint8)
 * Byte 25-26: Accel X in 0.01 m/s2 (int16)
 * Byte 27-28: Accel Y in 0.01 m/s2 (int16)
 * Byte 29-30: Accel Z in 0.01 m/s2 (int16)
 * Byte 31:    UV index (uint8, 0-15+)
 * Byte 32-33: Ambient lux (uint16)
 * Byte 34:    Acoustic event (uint8, 0=quiet, 1=event)
 */
function parseBinaryPayload(
    deviceId: string,
    receivedAt: string,
    frmPayload: string,
    rxMetadata?: Array<{ rssi?: number; snr?: number }>
): TelemetryData | null {
    try {
        const buffer = Buffer.from(frmPayload, 'base64');
        
        // Minimum required: GPS coordinates and altitude (12 bytes)
        if (buffer.length < 12) {
            console.error('Binary payload too short:', buffer.length);
            return null;
        }

        const rawLat = buffer.readInt32BE(0) / 1e7;
        const rawLon = buffer.readInt32BE(4) / 1e7;
        const rawAlt = buffer.readInt32BE(8);

        /* NOGPS power tier sentinel: firmware writes 0/0/0 when there's no fix.
         * Treat that as "no GPS data" rather than coordinates at Null Island. */
        const hasGpsFix = rawLat !== 0 && rawLon !== 0;
        const lat = hasGpsFix ? rawLat : null;
        const lon = hasGpsFix ? rawLon : null;
        const altitude_m = hasGpsFix ? rawAlt : null;

        // Extract receiver characteristics
        const rxData = rxMetadata && rxMetadata.length > 0 ? rxMetadata[0] : null;

        // Parse optional fields if available
        const temperature = buffer.length >= 14 ? buffer.readInt16BE(12) / 10 : null;
        const pressure = buffer.length >= 16 ? buffer.readUInt16BE(14) / 10 : null;
        const solar_voltage = buffer.length >= 18 ? buffer.readUInt16BE(16) / 1000 : null;
        const battery_voltage = buffer.length >= 20 ? buffer.readUInt16BE(18) / 1000 : null;
        const gps_speed = buffer.length >= 22 ? buffer.readUInt16BE(20) / 100 : null;
        const gps_heading = buffer.length >= 24 ? buffer.readUInt16BE(22) / 100 : null;
        const gps_satellites = buffer.length >= 25 ? buffer.readUInt8(24) : null;
        const mems_accel_x = buffer.length >= 27 ? buffer.readInt16BE(25) / 100 : null;
        const mems_accel_y = buffer.length >= 29 ? buffer.readInt16BE(27) / 100 : null;
        const mems_accel_z = buffer.length >= 31 ? buffer.readInt16BE(29) / 100 : null;
        const uv_index = buffer.length >= 32 ? buffer.readUInt8(31) : null;
        const ambient_lux = buffer.length >= 34 ? buffer.readUInt16BE(32) : null;
        const acoustic_event = buffer.length >= 35 ? buffer.readUInt8(34) : null;

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
        };
    } catch (error) {
        console.error('Error parsing binary payload:', error);
        return null;
    }
}
