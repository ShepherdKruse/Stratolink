/*
MIT License

Copyright (c) 2026 Stratolink (Nonprofit Organization)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

/* StratoLink TTN uplink formatter. Paste this entire ES5.1 file into TTN.
 * fPort 1: telemetry v1/v2/v3; 11: CTT v1/v2; 12: B2B v3.
 * No fleet keys are used: B2B CMAC authentication is NOT verified here.
 * See TTN_UPLINK_FORMATTER.md for units, limits and offline use. */

function slHex(bytes) {
    var result = "";
    for (var i = 0; i < bytes.length; i++) {
        result += (bytes[i] < 16 ? "0" : "") + bytes[i].toString(16);
    }
    return result;
}

function slU16(bytes, offset) {
    return bytes[offset] * 256 + bytes[offset + 1];
}

function slI16(bytes, offset) {
    var value = slU16(bytes, offset);
    return value >= 32768 ? value - 65536 : value;
}

function slU32(bytes, offset) {
    return bytes[offset] * 16777216 + bytes[offset + 1] * 65536 +
        bytes[offset + 2] * 256 + bytes[offset + 3];
}

function slI32(bytes, offset) {
    var value = slU32(bytes, offset);
    return value >= 2147483648 ? value - 4294967296 : value;
}

function slTelemetry(bytes) {
    if (bytes.length !== 35 && bytes.length !== 40) {
        throw new Error("Telemetry requires exactly 35 (v1) or 40 (v2/v3) bytes");
    }
    var lat = slI32(bytes, 0) / 1e7;
    var lon = slI32(bytes, 4) / 1e7;
    var altitude = slI32(bytes, 8);
    var speed = slU16(bytes, 20);
    var heading = slU16(bytes, 22);
    var satellites = bytes[24];
    var noGps = satellites === 0 && lat === 0 && lon === 0 && altitude === 0 &&
        speed === 0 && heading === 0;
    var gpsValid = satellites >= 4 && satellites <= 64 &&
        lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 &&
        altitude >= -500 && altitude <= 60000 && speed <= 50000 && heading <= 35999;
    if (!noGps && !gpsValid) {
        throw new Error("Invalid GPS state: expected atomic NOGPS or a qualified fix");
    }
    var accel = [slI16(bytes, 25), slI16(bytes, 27), slI16(bytes, 29)];
    var missingAxes = 0;
    for (var i = 0; i < accel.length; i++) if (accel[i] === -32768) missingAxes++;
    if (missingAxes !== 0 && missingAxes !== 3) {
        throw new Error("Invalid accelerometer state: mixed unavailable axes");
    }
    var word = bytes.length === 40 ? slU16(bytes, 36) : null;
    var version = bytes.length === 35 ? 1 : word !== 65535 && (word & 32768) ? 3 : 2;
    var status = bytes[34];
    var code = status & 15;
    var reset = (status >> 4) & 7;
    if ((version === 1 && status > 1) || (version >= 2 && (code === 15 || reset > 6))) {
        throw new Error("Reserved telemetry acoustic/power/reset status");
    }
    var temperature = slI16(bytes, 12);
    var pressure = slU16(bytes, 14);
    var lux = slU16(bytes, 32);
    var age = version === 3 ? word & 511 : version === 2 ? word : null;
    var speedMs = gpsValid ? speed / 100 : null;
    var headingDegrees = gpsValid ? heading / 100 : null;
    var activity = version >= 2 ? bytes[39] : 0;
    return {
        telemetry_version: version,
        gps_valid: gpsValid,
        lat: gpsValid ? lat : null,
        lon: gpsValid ? lon : null,
        altitude_m: gpsValid ? altitude : null,
        gps_speed: speedMs,
        gps_heading: headingDegrees,
        gps_satellites: satellites,
        velocity_x: gpsValid ? speedMs * Math.sin(headingDegrees * Math.PI / 180) : null,
        velocity_y: gpsValid ? speedMs * Math.cos(headingDegrees * Math.PI / 180) : null,
        temperature: temperature === -32768 ? null : temperature / 10,
        pressure: pressure === 65534 ? null : pressure / 10,
        solar_voltage: slU16(bytes, 16) / 1000,
        battery_voltage: slU16(bytes, 18) / 1000,
        mems_accel_x: missingAxes ? null : accel[0] / 100,
        mems_accel_y: missingAxes ? null : accel[1] / 100,
        mems_accel_z: missingAxes ? null : accel[2] / 100,
        uv_index: bytes[31] === 254 ? null : bytes[31],
        ambient_lux: lux === 65534 ? null : lux,
        acoustic_event: version === 1 ? status : code < 10 ? code & 1 : null,
        status_byte: version === 1 ? null : status,
        power_tier: version === 1 ? null : code < 10 ? code >> 1 : code - 10,
        reset_cause: version === 1 ? null : reset,
        boot_count: version === 1 ? null : bytes[35],
        gps_fix_age_min: (version === 3 && age === 511) || age === 65535 ? null : age,
        server_proof_count_mod8: version === 3 ? (word >> 12) & 7 : null,
        server_qualified_miss_streak: version === 3 ? (word >> 10) & 3 : null,
        server_recovery_parity: version === 3 ? (word >> 9) & 1 : null,
        command_ack_seq: version >= 2 && (status & 128) ? bytes[38] : null,
        relay_enabled: version >= 2 ? (activity & 128) !== 0 : null,
        relay_fwd_delta: version >= 2 ? (activity >> 4) & 7 : null,
        ctt_tags_delta: version >= 2 ? activity & 15 : null
    };
}

function slCtt(bytes, recvTime, warnings) {
    if (bytes.length !== 17) throw new Error("CTT requires exactly 17 bytes");
    if (bytes[0] !== 67 || bytes[1] !== 84) throw new Error("Invalid CTT magic");
    var version = bytes[2];
    if (version !== 1 && version !== 2) throw new Error("Unsupported CTT version: " + version);
    if (bytes[3] & 254) throw new Error("Reserved CTT flags are set");
    var motusValid = (bytes[3] & 1) !== 0;
    var motusId = slU32(bytes, 8);
    if ((!motusValid && motusId !== 0) || (motusValid && motusId > 1048575)) {
        throw new Error("Invalid CTT Motus dictionary ID/validity flag");
    }
    if (bytes[14] === 0) throw new Error("CTT hit count must be nonzero");
    var finalField = slU16(bytes, 15);
    var detectedAt = null;
    if (version === 2) {
        var receivedMs = recvTime && typeof recvTime.getTime === "function"
            ? recvTime.getTime() : typeof recvTime === "string" ? Date.parse(recvTime) : NaN;
        var detectionMs = receivedMs - finalField * 60000;
        if (isFinite(receivedMs) && isFinite(new Date(detectionMs).getTime())) {
            detectedAt = new Date(detectionMs).toISOString();
        } else {
            warnings.push("CTT recvTime missing or invalid; detected_at cannot be estimated");
        }
        if (finalField === 65535) {
            warnings.push("CTT detection age saturated; detected_at is only a latest-time estimate");
        }
    }
    return {
        event_version: version,
        raw_tag_id: slU32(bytes, 4),
        motus_tag_id: motusValid ? motusId : null,
        motus_valid: motusValid,
        detection_rssi: slI16(bytes, 12),
        hits: bytes[14],
        listen_window: version === 1 ? finalField : null,
        detection_age_min: version === 2 ? finalField : null,
        detection_age_saturated: version === 2 && finalField === 65535,
        detected_at: detectedAt
    };
}

function slB2b(bytes, warnings) {
    if (bytes.length < 9) throw new Error("B2B requires a complete 9-byte header");
    if (bytes[0] !== 83 || bytes[1] !== 66) throw new Error("Invalid B2B magic");
    if (bytes[2] !== 3) throw new Error("Unsupported B2B version: " + bytes[2]);
    if (slU16(bytes, 3) === 65535) throw new Error("B2B source cannot be broadcast");
    if (bytes[6] > 3) throw new Error("B2B TTL exceeds 3");
    if (bytes[7] & 252) throw new Error("Reserved B2B flags are set");
    if (bytes[8] > 44 || bytes.length !== 9 + bytes[8]) {
        throw new Error("B2B length mismatch or payload exceeds 53-byte frame limit");
    }
    if (bytes[8] < 8) throw new Error("B2B authentication trailer is missing");
    var type = bytes[7] & 3;
    var body = bytes.slice(9, bytes.length - 8);
    if (!((type === 0 && body.length > 0 && body.length % 6 === 0) ||
          (type === 1 && body.length >= 4) || (type === 2 && body.length === 3))) {
        throw new Error("Invalid B2B frame type or body length");
    }
    var crumbs = null;
    if (type === 0) {
        crumbs = [];
        for (var i = 0; i < body.length; i += 6) {
            var lat = slI16(body, i);
            var lon = slI16(body, i + 2);
            if (lat < -9000 || lat > 9000 || lon < -18000 || lon > 18000) {
                throw new Error("B2B crumb coordinates out of range");
            }
            crumbs.push({ lat: lat / 100, lon: lon / 100,
                altitude_m: body[i + 4] * 100, age_min: body[i + 5] });
        }
    }
    warnings.push("authentication_not_verified: formatter does not verify the B2B AES-CMAC");
    return {
        source_balloon_id: slU16(bytes, 3),
        message_id: bytes[5],
        ttl: bytes[6],
        frame_type: type === 0 ? "crumb" : type === 1 ? "command" : "ack",
        body_hex: slHex(body),
        auth_tag_hex: slHex(bytes.slice(bytes.length - 8)),
        authentication_verified: false,
        authentication_status: "authentication_not_verified",
        crumbs: crumbs,
        command_target: type === 1 || type === 2 ? slU16(body, 0) : null,
        command_opcode: type === 1 ? body[2] : null,
        command_seq: type === 1 ? body[3] : type === 2 ? body[2] : null,
        command_args_hex: type === 1 ? slHex(body.slice(4)) : null
    };
}

function decodeUplink(input) {
    var data = { decode_status: "invalid", f_port: input ? input.fPort : null,
        packet_type: "unknown", wire_version: null, payload_length: null,
        raw_hex: null, raw_bytes: null };
    var warnings = [];
    try {
        if (!input || !Array.isArray(input.bytes)) throw new Error("input.bytes must be a byte array");
        var bytes = input.bytes;
        for (var i = 0; i < bytes.length; i++) {
            if (typeof bytes[i] !== "number" || !isFinite(bytes[i]) ||
                Math.floor(bytes[i]) !== bytes[i] || bytes[i] < 0 || bytes[i] > 255) {
                throw new Error("input.bytes contains an invalid byte at index " + i);
            }
        }
        data.raw_hex = slHex(bytes);
        data.raw_bytes = bytes.slice(0);
        data.payload_length = bytes.length;
        var decoded;
        if (input.fPort === 1) {
            data.packet_type = "telemetry";
            if (bytes.length === 35) data.wire_version = 1;
            if (bytes.length === 40) {
                var word = slU16(bytes, 36);
                data.wire_version = word !== 65535 && (word & 32768) ? 3 : 2;
            }
            decoded = slTelemetry(bytes);
        } else if (input.fPort === 11) {
            data.packet_type = "ctt_event";
            if (bytes.length >= 3) data.wire_version = bytes[2];
            decoded = slCtt(bytes, input.recvTime, warnings);
        } else if (input.fPort === 12) {
            data.packet_type = "b2b_event";
            if (bytes.length >= 3) data.wire_version = bytes[2];
            decoded = slB2b(bytes, warnings);
        } else {
            throw new Error("Unsupported fPort: " + input.fPort);
        }
        for (var key in decoded) {
            if (Object.prototype.hasOwnProperty.call(decoded, key)) data[key] = decoded[key];
        }
        data.decode_status = "decoded";
        return { data: data, warnings: warnings };
    } catch (error) {
        return { data: data, errors: [error.message], warnings: warnings };
    }
}
