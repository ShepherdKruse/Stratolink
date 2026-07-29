import assert from 'node:assert/strict';

import {
    parseB2BEventPayload,
    parseCTTEventPayload,
    parseTTNPayload,
    type TTNWebhookPayload,
} from './payload-parser.ts';

function webhook(fPort: number, bytes: number[]): TTNWebhookPayload {
    return {
        end_device_ids: { device_id: 'host-vector' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: {
            f_port: fPort,
            frm_payload: Buffer.from(bytes).toString('base64'),
            rx_metadata: [{ rssi: -87, snr: 5.5 }],
            settings: {
                data_rate: {
                    lora: { spreading_factor: 9, bandwidth: 125000 },
                },
                frequency: '903900000',
            },
        },
    };
}

/* Exact vector emitted by firmware/src/ctt_event.cpp and asserted by its
 * strict host test. */
const ctt = [
    0x43, 0x54, 0x02, 0x01,
    0x80, 0x7F, 0x00, 0xFF,
    0x00, 0x0A, 0xBC, 0xDE,
    0xFF, 0x93, 0x07, 0x12, 0x34,
];
const parsedCtt = parseCTTEventPayload(webhook(11, ctt));
assert(parsedCtt);
assert.equal(parsedCtt.raw_tag_id, 0x807F00FF);
assert.equal(parsedCtt.motus_tag_id, 0xABCDE);
assert.equal(parsedCtt.detection_rssi, -109);
assert.equal(parsedCtt.event_version, 2);
assert.equal(parsedCtt.detection_age_min, 0x1234);
assert.equal(parsedCtt.detected_at, '2026-07-21T18:20:00.000Z');
assert.equal(parsedCtt.time, parsedCtt.detected_at);
assert.equal(parsedCtt.listen_window, null);
assert.equal(parsedCtt.lora_sf, 9);
assert.equal(parsedCtt.lora_bw, 125000);
assert.equal(parsedCtt.frequency_hz, 903900000);
assert.equal(parseCTTEventPayload(webhook(12, ctt)), null);

/* TTN radio metadata is observability, not payload authority. Malformed
 * numeric prefixes and physically impossible values must become null rather
 * than plausible-looking link evidence. */
const malformedRadio = webhook(11, ctt);
malformedRadio.uplink_message!.settings = {
    data_rate: {
        lora: {
            spreading_factor: 9.5,
            bandwidth: Number.NaN,
        },
    },
    frequency: '903900000garbage',
};
const parsedMalformedRadio = parseCTTEventPayload(malformedRadio);
assert(parsedMalformedRadio);
assert.equal(parsedMalformedRadio.lora_sf, null);
assert.equal(parsedMalformedRadio.lora_bw, null);
assert.equal(parsedMalformedRadio.frequency_hz, null);

const outOfRangeRadio = webhook(11, ctt);
outOfRangeRadio.uplink_message!.settings = {
    data_rate: {
        lora: { spreading_factor: 13, bandwidth: 501000 },
    },
    frequency: 1000000001,
};
const parsedOutOfRangeRadio = parseCTTEventPayload(outOfRangeRadio);
assert(parsedOutOfRangeRadio);
assert.equal(parsedOutOfRangeRadio.lora_sf, null);
assert.equal(parsedOutOfRangeRadio.lora_bw, null);
assert.equal(parsedOutOfRangeRadio.frequency_hz, null);

const legacyCtt = [...ctt];
legacyCtt[2] = 1;
const parsedLegacyCtt = parseCTTEventPayload(webhook(11, legacyCtt));
assert(parsedLegacyCtt);
assert.equal(parsedLegacyCtt.event_version, 1);
assert.equal(parsedLegacyCtt.listen_window, 0x1234);
assert.equal(parsedLegacyCtt.detection_age_min, null);
assert.equal(parsedLegacyCtt.detected_at, null);

const futureCtt = [...ctt];
futureCtt[2] = 3;
assert.equal(parseCTTEventPayload(webhook(11, futureCtt)), null);

/* Firmware initializes a real detection at one hit and saturates upward.
 * Reject zero here so malformed wire data becomes a client error instead of
 * reaching the database's hits>=1 constraint and surfacing as HTTP 500. */
const zeroHitCtt = [...ctt];
zeroHitCtt[14] = 0;
assert.equal(parseCTTEventPayload(webhook(11, zeroHitCtt)), null);

/* Exact wire-v3 crumb layout emitted by b2b_encode(): SB, version, source,
 * msg_id, ttl, type, len, then the 6-byte packed crumb and opaque 8-byte
 * AES-CMAC trailer. The receiving balloon has verified the tag before tunnel. */
const crumb = [
    0x53, 0x42, 0x03, 0x00, 0x02, 0x01, 0x03, 0x00, 0x0E,
    0x0E, 0xA1, 0xD0, 0x2E, 0xB4, 0x03,
    0xC1, 0x67, 0xEB, 0x8C, 0xE4, 0x7F, 0x19, 0x3D,
];
const parsedCrumb = parseB2BEventPayload(webhook(12, crumb));
assert(parsedCrumb);
assert.deepEqual(parsedCrumb.crumbs, [{
    lat: 37.45,
    lon: -122.42,
    altitude_m: 18000,
    age_min: 3,
}]);
assert.equal(
    parsedCrumb.payload_base64,
    Buffer.from(crumb.slice(9, 15)).toString('base64'),
);

/* The largest legal B2B tunnel is exactly the US915 DR1 application ceiling:
 * 9-byte header + 44-byte control payload = 53 bytes. */
const maxFrame = [
    0x53, 0x42, 0x03, 0x00, 0x02, 0x07, 0x03, 0x01, 0x2C,
    ...new Array(44).fill(0),
];
assert.equal(maxFrame.length, 53);
assert(parseB2BEventPayload(webhook(12, maxFrame)));

const oversized = [
    0x53, 0x42, 0x03, 0x00, 0x02, 0x08, 0x03, 0x01, 0x2D,
    ...new Array(45).fill(0),
];
assert.equal(parseB2BEventPayload(webhook(12, oversized)), null);

const overTtl = [...crumb];
overTtl[6] = 4;
assert.equal(parseB2BEventPayload(webhook(12, overTtl)), null);

const impossibleCrumb = [...crumb];
impossibleCrumb[9] = 0x23;
impossibleCrumb[10] = 0x29; // +90.01 degrees
assert.equal(parseB2BEventPayload(webhook(12, impossibleCrumb)), null);
assert.equal(parseB2BEventPayload(webhook(11, crumb)), null);

const legacyV2 = [...crumb];
legacyV2[2] = 2;
assert.equal(parseB2BEventPayload(webhook(12, legacyV2)), null);

const missingTag = [...crumb.slice(0, 15)];
missingTag[8] = 6;
assert.equal(parseB2BEventPayload(webhook(12, missingTag)), null);
const broadcastSource = [...crumb];
broadcastSource[3] = 0xFF;
broadcastSource[4] = 0xFF;
assert.equal(parseB2BEventPayload(webhook(12, broadcastSource)), null);

const command = [
    0x53, 0x42, 0x03, 0x00, 0x02, 0x02, 0x02, 0x01, 0x0D,
    0x00, 0x01, 0x02, 0x2A, 0x01,
    ...new Array(8).fill(0xA5),
];
const parsedCommand = parseB2BEventPayload(webhook(12, command));
assert(parsedCommand);
assert.equal(parsedCommand.command_target, 1);
assert.equal(parsedCommand.command_opcode, 2);
assert.equal(parsedCommand.command_seq, 42);

const ack = [
    0x53, 0x42, 0x03, 0x00, 0x02, 0x03, 0x01, 0x02, 0x0B,
    0x00, 0x07, 0x2A,
    ...new Array(8).fill(0x5A),
];
const parsedAck = parseB2BEventPayload(webhook(12, ack));
assert(parsedAck);
assert.equal(parsedAck.command_target, 7);
assert.equal(parsedAck.command_opcode, null);
assert.equal(parsedAck.command_seq, 42);

function binaryTelemetry(latE7: number, lonE7: number, altitude: number,
                         satellites: number): TTNWebhookPayload {
    const bytes = Buffer.alloc(35);
    bytes.writeInt32BE(latE7, 0);
    bytes.writeInt32BE(lonE7, 4);
    bytes.writeInt32BE(altitude, 8);
    bytes.writeUInt8(satellites, 24);
    return webhook(1, [...bytes]);
}

const equator = parseTTNPayload(binaryTelemetry(0, 100000000, 100, 7));
assert(equator);
assert.equal(equator.lat, 0);
assert.equal(equator.lon, 10);

const greenwich = parseTTNPayload(binaryTelemetry(100000000, 0, 100, 7));
assert(greenwich);
assert.equal(greenwich.lat, 10);
assert.equal(greenwich.lon, 0);

const realNullIsland = parseTTNPayload(binaryTelemetry(0, 0, 0, 7));
assert(realNullIsland);
assert.equal(realNullIsland.lat, 0);
assert.equal(realNullIsland.lon, 0);

const noGps = parseTTNPayload(binaryTelemetry(0, 0, 0, 0));
assert(noGps);
assert.equal(noGps.lat, null);
assert.equal(noGps.lon, null);
assert.equal(noGps.altitude_m, null);
assert.equal(noGps.gps_speed, null);
assert.equal(noGps.gps_heading, null);
assert.equal(noGps.velocity_x, null);
assert.equal(noGps.velocity_y, null);
assert.equal(noGps.telemetry_version, 1);
assert.equal(noGps.power_tier, null);

function jsonTelemetry(decoded_payload: Record<string, unknown>): TTNWebhookPayload {
    return {
        end_device_ids: { device_id: 'host-json-vector' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: {
            f_port: 1,
            decoded_payload,
            rx_metadata: [{ rssi: -87, snr: 5.5 }],
        },
    };
}

const jsonNoGps = parseTTNPayload(jsonTelemetry({
    gps_fix: false,
    latitude: 0,
    longitude: 0,
    altitude_m: 0,
    gps_satellites: 0,
    gps_speed: 0,
    gps_heading: 0,
    velocity_x: 0,
    velocity_y: 0,
}));
assert(jsonNoGps);
assert.equal(jsonNoGps.lat, null);
assert.equal(jsonNoGps.altitude_m, null);
assert.equal(jsonNoGps.gps_speed, null);
assert.equal(jsonNoGps.gps_heading, null);
assert.equal(jsonNoGps.velocity_x, null);
assert.equal(jsonNoGps.velocity_y, null);
assert.equal(jsonNoGps.gps_satellites, 0);

const jsonNullIslandFix = parseTTNPayload(jsonTelemetry({
    gps_fix: true,
    latitude: 0,
    longitude: 0,
    altitude_m: 0,
    gps_satellites: 7,
    gps_speed: 10,
    gps_heading: 90,
}));
assert(jsonNullIslandFix);
assert.equal(jsonNullIslandFix.lat, 0);
assert.equal(jsonNullIslandFix.lon, 0);
assert(Math.abs((jsonNullIslandFix.velocity_x ?? 0) - 10) < 1e-12);
assert(Math.abs(jsonNullIslandFix.velocity_y ?? 1) < 1e-12);

/* JSON-only formatters get no weaker contract than raw wire bytes. */
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: false,
    latitude: 10,
    longitude: 20,
    altitude_m: 100,
    gps_satellites: 7,
    gps_speed: 12,
    gps_heading: 45,
})), null);
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: true,
    latitude: 10,
    longitude: 20,
    altitude_m: 100,
    gps_speed: 12,
    gps_heading: 45,
})), null);
assert.equal(parseTTNPayload(jsonTelemetry({})), null);
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: false,
    latitude: 0,
    longitude: 0,
    altitude_m: 0,
    gps_satellites: 0,
    gps_heading: 0,
    /* Missing speed is not a complete firmware NOGPS sentinel. */
})), null);
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: true,
    /* Missing latitude must not become a real Null Island coordinate. */
    longitude: 0,
    altitude_m: 0,
    gps_satellites: 7,
    gps_speed: 10,
    gps_heading: 90,
})), null);
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: true,
    latitude: 10,
    longitude: 20,
    altitude_m: 100,
    gps_satellites: '7cached',
    gps_speed: 12,
    gps_heading: 45,
})), null);
assert.equal(parseTTNPayload(jsonTelemetry({
    gps_fix: true,
    latitude: 10,
    longitude: 20,
    altitude_m: 100,
    gps_satellites: 3,
    gps_speed: 12,
    gps_heading: 45,
})), null);

/* Raw telemetry must be either the firmware's complete all-zero NOGPS
 * sentinel or a fully value-gated fix. Mixed cached-looking states are
 * rejected instead of being stored as a nominal no-fix row. */
assert.equal(parseTTNPayload(binaryTelemetry(100000000, 200000000, 100, 3)), null);
assert.equal(parseTTNPayload(binaryTelemetry(0, 0, 0, 3)), null);
assert.equal(parseTTNPayload(binaryTelemetry(0, 0, 0, 65)), null);
assert.equal(parseTTNPayload(binaryTelemetry(0, 0, 60001, 7)), null);
const noGpsWithCachedSpeed = Buffer.alloc(35);
noGpsWithCachedSpeed.writeUInt16BE(100, 20);
assert.equal(parseTTNPayload(webhook(1, [...noGpsWithCachedSpeed])), null);
const invalidHeading = Buffer.from(
    Buffer.from(binaryTelemetry(100000000, 200000000, 100, 7)
        .uplink_message!.frm_payload!, 'base64')
);
invalidHeading.writeUInt16BE(36000, 22);
assert.equal(parseTTNPayload(webhook(1, [...invalidHeading])), null);

const v2 = Buffer.alloc(40);
v2.writeInt32BE(377749000, 0);
v2.writeInt32BE(-1224194000, 4);
v2.writeInt32BE(12345, 8);
v2.writeUInt8(8, 24);
v2.writeUInt8(0x80 | (2 << 4) | (1 << 1) | 1, 34);
v2.writeUInt8(17, 35);
v2.writeUInt16BE(0x1234, 36);
v2.writeUInt8(0xA6, 38);
v2.writeUInt8(0x80 | (6 << 4) | 11, 39);
const parsedV2 = parseTTNPayload(webhook(1, [...v2]));
assert(parsedV2);
assert.equal(parsedV2.telemetry_version, 2);
assert.equal(parsedV2.acoustic_event, 1);
assert.equal(parsedV2.power_tier, 1);
assert.equal(parsedV2.reset_cause, 2);
assert.equal(parsedV2.boot_count, 17);
assert.equal(parsedV2.gps_fix_age_min, 0x1234);
assert.equal(parsedV2.command_ack_seq, 0xA6);
assert.equal(parsedV2.relay_enabled, true);
assert.equal(parsedV2.relay_fwd_delta, 6);
assert.equal(parsedV2.ctt_tags_delta, 11);

for (let tier = 0; tier <= 4; tier += 1) {
    const micUnavailable = Buffer.from(v2);
    micUnavailable[34] = (micUnavailable[34] & 0xF0) | (10 + tier);
    const parsedMicUnavailable = parseTTNPayload(
        webhook(1, [...micUnavailable]));
    assert(parsedMicUnavailable);
    assert.equal(parsedMicUnavailable.acoustic_event, null);
    assert.equal(parsedMicUnavailable.power_tier, tier);
    assert.equal(parsedMicUnavailable.reset_cause, 2);
}

const unavailableSensors = Buffer.from(v2);
unavailableSensors.writeInt16BE(-32768, 12);
unavailableSensors.writeUInt16BE(0xFFFE, 14);
unavailableSensors.writeInt16BE(-32768, 25);
unavailableSensors.writeInt16BE(-32768, 27);
unavailableSensors.writeInt16BE(-32768, 29);
unavailableSensors.writeUInt8(0xFE, 31);
unavailableSensors.writeUInt16BE(0xFFFE, 32);
const parsedUnavailableSensors = parseTTNPayload(
    webhook(1, [...unavailableSensors]));
assert(parsedUnavailableSensors);
assert.equal(parsedUnavailableSensors.temperature, null);
assert.equal(parsedUnavailableSensors.pressure, null);
assert.equal(parsedUnavailableSensors.mems_accel_x, null);
assert.equal(parsedUnavailableSensors.mems_accel_y, null);
assert.equal(parsedUnavailableSensors.mems_accel_z, null);
assert.equal(parsedUnavailableSensors.uv_index, null);
assert.equal(parsedUnavailableSensors.ambient_lux, null);

const mixedAccelValidity = Buffer.from(unavailableSensors);
mixedAccelValidity.writeInt16BE(0, 27);
assert.equal(parseTTNPayload(webhook(1, [...mixedAccelValidity])), null);

/* Raw application bytes remain authoritative if TTN is still running an old
 * formatter. This prevents a formatter rollout lag from hiding v2 health and
 * command acknowledgement fields that are present on the signed wire. */
const rawWithStaleFormatter = webhook(1, [...v2]);
rawWithStaleFormatter.uplink_message!.decoded_payload = {
    latitude: 1,
    longitude: 2,
    gps_satellites: 7,
    telemetry_version: 1,
};
const authoritativeRaw = parseTTNPayload(rawWithStaleFormatter);
assert(authoritativeRaw);
assert.equal(authoritativeRaw.lat, 37.7749);
assert.equal(authoritativeRaw.telemetry_version, 2);
assert.equal(authoritativeRaw.command_ack_seq, 0xA6);

const v2NoFixOrCommand = Buffer.from(v2);
v2NoFixOrCommand[34] &= 0x7F;
v2NoFixOrCommand.writeUInt16BE(0xFFFF, 36);
v2NoFixOrCommand[38] = 0;
const parsedV2NoFixOrCommand = parseTTNPayload(
    webhook(1, [...v2NoFixOrCommand]));
assert(parsedV2NoFixOrCommand);
assert.equal(parsedV2NoFixOrCommand.gps_fix_age_min, null);
assert.equal(parsedV2NoFixOrCommand.command_ack_seq, null);

const invalidTier = Buffer.from(v2);
invalidTier[34] = (invalidTier[34] & ~0x0E) | (7 << 1);
assert.equal(parseTTNPayload(webhook(1, [...invalidTier])), null);
const invalidReset = Buffer.from(v2);
invalidReset[34] = (invalidReset[34] & ~0x70) | (7 << 4);
assert.equal(parseTTNPayload(webhook(1, [...invalidReset])), null);
assert.equal(parseTTNPayload(webhook(1, new Array(34).fill(0))), null);
assert.equal(parseTTNPayload(webhook(1, new Array(36).fill(0))), null);
assert.equal(parseTTNPayload(webhook(1, new Array(39).fill(0))), null);
assert.equal(parseTTNPayload(webhook(1, new Array(41).fill(0))), null);

const jsonEquator = parseTTNPayload({
    end_device_ids: { device_id: 'json-equator' },
    uplink_message: {
        decoded_payload: {
            latitude: 0,
            longitude: 10,
            altitude_m: 100,
            gps_satellites: 7,
            gps_speed: 0,
            gps_heading: 0,
        },
    },
});
assert(jsonEquator);
assert.equal(jsonEquator.lat, 0);
assert.equal(jsonEquator.lon, 10);

console.log('firmware-to-web telemetry v1/v2, CTT/B2B, DR1, and GPS edge cases passed');
