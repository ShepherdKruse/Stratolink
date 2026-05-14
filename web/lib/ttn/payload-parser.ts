/**
 * TTN Payload Parser
 * 
 * Handles parsing of telemetry data from The Things Network webhook payloads.
 * Supports both JSON (via TTN Payload Formatter) and binary formats.
 */

export interface TelemetryData {
    device_id: string;
    time: string;
    lat: number;
    lon: number;
    altitude_m: number;
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

    // Try JSON format first (TTN Payload Formatter)
    if (uplinkMessage.decoded_payload) {
        return parseJSONPayload(deviceId, receivedAt, uplinkMessage.decoded_payload, uplinkMessage.rx_metadata);
    }

    // Fall back to binary format
    if (uplinkMessage.frm_payload) {
        return parseBinaryPayload(deviceId, receivedAt, uplinkMessage.frm_payload, uplinkMessage.rx_metadata);
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

    return {
        device_id: deviceId,
        time: receivedAt,
        lat: parseFloat(decoded.latitude) || parseFloat(decoded.lat) || 0,
        lon: parseFloat(decoded.longitude) || parseFloat(decoded.lon) || 0,
        altitude_m: parseFloat(decoded.altitude) || parseFloat(decoded.altitude_m) || 0,
        velocity_x: decoded.velocity_x !== undefined ? parseFloat(decoded.velocity_x) : null,
        velocity_y: decoded.velocity_y !== undefined ? parseFloat(decoded.velocity_y) : null,
        temperature: decoded.temperature !== undefined ? parseFloat(decoded.temperature) : null,
        pressure: decoded.pressure !== undefined ? parseFloat(decoded.pressure) : null,
        solar_voltage: decoded.solar_voltage !== undefined ? parseFloat(decoded.solar_voltage) : null,
        battery_voltage: decoded.battery_voltage !== undefined ? parseFloat(decoded.battery_voltage) : null,
        rssi: rxData?.rssi !== undefined ? parseFloat(String(rxData.rssi)) : decoded.rssi !== undefined ? parseFloat(decoded.rssi) : null,
        snr: rxData?.snr !== undefined ? parseFloat(String(rxData.snr)) : decoded.snr !== undefined ? parseFloat(decoded.snr) : null,
        gps_speed: decoded.gps_speed !== undefined ? parseFloat(decoded.gps_speed) : null,
        gps_heading: decoded.gps_heading !== undefined ? parseFloat(decoded.gps_heading) : null,
        gps_satellites: decoded.gps_satellites !== undefined ? parseInt(String(decoded.gps_satellites)) : null,
        mems_accel_x: decoded.mems_accel_x !== undefined ? parseFloat(decoded.mems_accel_x) : null,
        mems_accel_y: decoded.mems_accel_y !== undefined ? parseFloat(decoded.mems_accel_y) : null,
        mems_accel_z: decoded.mems_accel_z !== undefined ? parseFloat(decoded.mems_accel_z) : null,
        uv_index: decoded.uv_index !== undefined ? parseInt(String(decoded.uv_index)) : null,
        ambient_lux: decoded.ambient_lux !== undefined ? parseFloat(decoded.ambient_lux) : null,
        acoustic_event: decoded.acoustic_event !== undefined ? parseInt(String(decoded.acoustic_event), 10) : null,
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

        const lat = buffer.readInt32BE(0) / 1e7;
        const lon = buffer.readInt32BE(4) / 1e7;
        const altitude_m = buffer.readInt32BE(8);

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
