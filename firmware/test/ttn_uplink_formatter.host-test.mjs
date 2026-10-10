import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { test } from 'node:test';
import { parseTTNPayload, parseCTTEventPayload, parseB2BEventPayload }
    from '../../web/lib/ttn/payload-parser.ts';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const formatter = join(root, 'web/public/assets/docs/ttn-uplink-formatter.js');
const receivedAt = '2026-07-25T00:00:00.000Z';
const vectors = new Map();
const build = mkdtempSync(join(tmpdir(), 'stratolink-ttn-vectors-'));
try {
    const binary = join(build, 'vectors');
    execFileSync(process.env.CXX || 'c++', [
        '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I', join(root, 'firmware/include'), '-I', join(root, 'firmware/src'),
        join(here, 'generate_ttn_uplink_vectors.cpp'),
        ...['telemetry.cpp', 'ctt_event.cpp', 'b2b.cpp', 'crypto_aes128.cpp']
            .map(name => join(root, 'firmware/src', name)),
        '-o', binary,
    ]);
    for (const line of execFileSync(binary, { encoding: 'utf8' }).trim().split('\n')) {
        const vector = JSON.parse(line);
        vectors.set(vector.name, vector);
    }
} finally {
    rmSync(build, { recursive: true });
}

function decode(bytes, fPort = 1, recvTime = new Date(receivedAt)) {
    assert(existsSync(formatter), 'install-ready TTN formatter is missing');
    const context = vm.createContext({}); // No Buffer, require, process, or module.
    vm.runInContext(readFileSync(formatter, 'utf8'), context);
    const result = context.decodeUplink({ bytes, fPort, recvTime });
    return JSON.parse(JSON.stringify(result));
}

function good(bytes, fPort = 1, recvTime) {
    const result = decode(bytes, fPort, recvTime);
    assert.deepEqual(result.errors || [], []);
    assert.equal(result.data.raw_hex, Buffer.from(bytes).toString('hex'));
    assert.deepEqual(result.data.raw_bytes, bytes);
    assert.equal(result.data.f_port, fPort);
    assert.equal(result.data.payload_length, bytes.length);
    assert.equal(result.data.decode_status, 'decoded');
    return result;
}

function bad(bytes, fPort = 1) {
    const result = decode(bytes, fPort);
    assert(result.errors?.length, 'malformed packet must return an error');
    assert.equal(result.data.decode_status, 'invalid');
    assert.equal(result.data.raw_hex, Buffer.from(bytes).toString('hex'));
    assert.equal(result.data.lat, undefined);
    assert.equal(result.data.crumbs, undefined);
}

function edited(name, edit) {
    const bytes = [...vectors.get(name).bytes];
    edit(bytes);
    return bytes;
}

test('compiled firmware packets decode all primary sensor and health fields', () => {
    const { bytes } = vectors.get('primary_v3');
    const data = good(bytes).data;
    const expected = {
        packet_type: 'telemetry', telemetry_version: 3, wire_version: 3,
        lat: 37.45, lon: -122.42, altitude_m: 18000,
        temperature: -12.3, pressure: 1012.7, solar_voltage: 5.123,
        battery_voltage: 4.66, gps_speed: 12.34, gps_heading: 90,
        gps_satellites: 12, gps_valid: true,
        mems_accel_x: -1.23, mems_accel_y: 0, mems_accel_z: 9.81,
        uv_index: 5, ambient_lux: 23456, acoustic_event: 1,
        status_byte: 213, power_tier: 2, reset_cause: 5, boot_count: 17,
        gps_fix_age_min: 291, server_proof_count_mod8: 5,
        server_qualified_miss_streak: 2, server_recovery_parity: 1,
        command_ack_seq: 42, relay_enabled: true, relay_fwd_delta: 6,
        ctt_tags_delta: 11,
    };
    for (const [key, value] of Object.entries(expected)) assert.equal(data[key], value, key);
    assert.equal(data.velocity_x, 12.34);
    assert(Math.abs(data.velocity_y) < 1e-12);
});

test('NOGPS, unavailable sensors and v3 reserved-word collision stay distinguishable', () => {
    const data = good(vectors.get('primary_nogps').bytes).data;
    for (const field of ['lat', 'lon', 'altitude_m', 'gps_speed', 'gps_heading',
        'velocity_x', 'velocity_y', 'temperature', 'pressure', 'mems_accel_x',
        'mems_accel_y', 'mems_accel_z', 'uv_index', 'ambient_lux', 'acoustic_event',
        'gps_fix_age_min', 'command_ack_seq']) assert.equal(data[field], null, field);
    assert.equal(data.gps_valid, false);
    assert.equal(data.gps_satellites, 0);
    assert.equal(data.power_tier, 4);
    assert.equal(data.status_byte, 14);
    assert.equal(data.wire_version, 3);
    assert.equal(data.server_proof_count_mod8, 6);
    assert.equal(data.server_qualified_miss_streak, 3);
    assert.equal(data.server_recovery_parity, 1);
});

test('legacy v1 and v2 keep historical status and fix-age semantics', () => {
    const v1 = vectors.get('primary_v3').bytes.slice(0, 35);
    v1[34] = 1;
    const old = good(v1).data;
    assert.equal(old.telemetry_version, 1);
    assert.equal(old.acoustic_event, 1);
    assert.equal(old.status_byte, null);
    for (const key of ['power_tier', 'reset_cause', 'boot_count', 'gps_fix_age_min',
        'server_proof_count_mod8', 'command_ack_seq', 'relay_enabled']) {
        assert.equal(old[key], null, key);
    }
    for (const [word, age] of [[0x1234, 4660], [0x7fff, 32767], [0xffff, null]]) {
        const v2 = edited('primary_v3', b => { b[36] = word >> 8; b[37] = word & 255; });
        const data = good(v2).data;
        assert.equal(data.telemetry_version, 2);
        assert.equal(data.status_byte, 213);
        assert.equal(data.gps_fix_age_min, age);
        assert.equal(data.server_proof_count_mod8, null);
    }
});

test('GPS boundaries, equator/Greenwich and valid zero coordinates are accepted', () => {
    const base = vectors.get('primary_v3').bytes;
    for (const [lat, lon, alt, speed, heading, sats] of [
        [0, 0, 0, 0, 0, 4], [-900000000, -1800000000, -500, 50000, 35999, 64],
        [900000000, 1800000000, 60000, 0, 0, 4], [0, 100000000, 1, 0, 0, 4],
        [100000000, 0, 1, 0, 0, 4],
    ]) {
        const bytes = Buffer.from(base);
        bytes.writeInt32BE(lat, 0); bytes.writeInt32BE(lon, 4); bytes.writeInt32BE(alt, 8);
        bytes.writeUInt16BE(speed, 20); bytes.writeUInt16BE(heading, 22); bytes[24] = sats;
        const data = good([...bytes]).data;
        assert.equal(data.lat, lat / 1e7); assert.equal(data.lon, lon / 1e7);
        assert.equal(data.altitude_m, alt); assert.equal(data.gps_valid, true);
    }
});

test('sensor saturation remains numeric and every acoustic power status is decoded', () => {
    for (let code = 0; code < 15; ++code) {
        const bytes = edited('primary_v3', b => {
            b[34] = code; b[31] = 255; b[32] = 255; b[33] = 255;
        });
        const data = good(bytes).data;
        assert.equal(data.uv_index, 255); assert.equal(data.ambient_lux, 65535);
        assert.equal(data.power_tier, code < 10 ? code >> 1 : code - 10);
        assert.equal(data.acoustic_event, code < 10 ? code & 1 : null);
        assert.equal(data.command_ack_seq, null);
    }
});

test('CTT v2 age, v1 listen window and unsigned raw tag IDs decode accurately', () => {
    const bytes = vectors.get('ctt_v2').bytes;
    const data = good(bytes, 11).data;
    assert.equal(data.packet_type, 'ctt_event'); assert.equal(data.event_version, 2);
    assert.equal(data.raw_tag_id, 0x807f00ff); assert.equal(data.motus_tag_id, 0xabcde);
    assert.equal(data.detection_rssi, -109); assert.equal(data.hits, 7);
    assert.equal(data.detection_age_min, 4660);
    assert.equal(data.detected_at, '2026-07-21T18:20:00.000Z');
    assert.equal(data.listen_window, null);
    const legacy = good(edited('ctt_v2', b => { b[2] = 1; }), 11).data;
    assert.equal(legacy.event_version, 1); assert.equal(legacy.listen_window, 4660);
    assert.equal(legacy.detected_at, null); assert.equal(legacy.detection_age_min, null);
    const saturated = good(vectors.get('ctt_saturated').bytes, 11);
    assert.equal(saturated.data.motus_valid, false); assert.equal(saturated.data.motus_tag_id, null);
    assert.equal(saturated.data.detection_age_min, 65535);
    assert(saturated.warnings.some(w => /saturat/i.test(w)));
    const noTime = good(bytes, 11, null);
    assert.equal(noTime.data.detected_at, null);
    assert(noTime.warnings.some(w => /recvTime/.test(w)));
});

test('B2B crumbs/control fields exclude the CMAC trailer and never assert authentication', () => {
    for (const name of ['b2b_crumb', 'b2b_six_crumbs', 'b2b_command', 'b2b_ack']) {
        const { bytes } = vectors.get(name);
        const result = good(bytes, 12);
        assert.equal(result.data.packet_type, 'b2b_event');
        assert.equal(result.data.wire_version, 3);
        assert.equal(result.data.source_balloon_id, 2);
        assert.equal(result.data.message_id, 7); assert.equal(result.data.ttl, 3);
        assert.equal(result.data.authentication_verified, false);
        assert.equal(result.data.authentication_status, 'authentication_not_verified');
        assert(result.warnings.some(w => /authentication_not_verified/.test(w)));
        assert.equal(result.data.auth_tag_hex, Buffer.from(bytes.slice(-8)).toString('hex'));
        assert.equal(result.data.body_hex, Buffer.from(bytes.slice(9, -8)).toString('hex'));
    }
    const crumb = good(vectors.get('b2b_crumb').bytes, 12).data;
    assert.deepEqual(crumb.crumbs, [{ lat: 37.45, lon: -122.42, altitude_m: 18000, age_min: 3 }]);
    assert.equal(good(vectors.get('b2b_six_crumbs').bytes, 12).data.crumbs.length, 6);
    const command = good(vectors.get('b2b_command').bytes, 12).data;
    assert.equal(command.frame_type, 'command'); assert.equal(command.command_target, 1);
    assert.equal(command.command_opcode, 2); assert.equal(command.command_seq, 42);
    assert.equal(command.command_args_hex, '01');
    const ack = good(vectors.get('b2b_ack').bytes, 12).data;
    assert.equal(ack.frame_type, 'ack'); assert.equal(ack.command_target, 7);
    assert.equal(ack.command_opcode, null); assert.equal(ack.command_seq, 42);
    const tampered = good(edited('b2b_crumb', b => { b[b.length - 1] ^= 1; }), 12);
    assert.equal(tampered.data.authentication_verified, false);
});

test('formatter fields agree with existing parser for every compiled firmware vector', () => {
    for (const { bytes, fPort, name } of vectors.values()) {
        const data = good(bytes, fPort).data;
        const webhook = {
            end_device_ids: { device_id: 'host-vector' }, received_at: receivedAt,
            uplink_message: { f_port: fPort, frm_payload: Buffer.from(bytes).toString('base64') },
        };
        const parser = fPort === 1 ? parseTTNPayload : fPort === 11 ? parseCTTEventPayload : parseB2BEventPayload;
        const parsed = parser(webhook);
        assert(parsed, name);
        const metadata = ['device_id', 'time', 'rssi', 'snr', 'link_rssi', 'link_snr',
            'lora_sf', 'lora_bw', 'frequency_hz', 'payload_base64', 'raw_frame_base64'];
        for (const [key, value] of Object.entries(parsed)) {
            if (!metadata.includes(key)) assert.deepEqual(data[key], value, `${name}.${key}`);
        }
    }
});

test('truncations, unknown ports/versions, reserved flags and invalid shapes fail closed', () => {
    for (const { bytes, fPort } of vectors.values()) {
        for (let length = 0; length < bytes.length; ++length) bad(bytes.slice(0, length), fPort);
        bad([...bytes, 0], fPort);
    }
    bad(vectors.get('primary_v3').bytes, 99);
    bad(vectors.get('ctt_v2').bytes, 1);
    for (const [index, value] of [[0, 0], [2, 3], [3, 2], [8, 1], [14, 0]]) {
        bad(edited('ctt_v2', b => { b[index] = value; }), 11);
    }
    bad(edited('ctt_v2', b => { b[3] = 0; }), 11);
    for (const [index, value] of [[0, 0], [2, 2], [2, 4], [6, 4], [7, 3], [7, 4], [8, 45], [9, 0x7f]]) {
        bad(edited('b2b_crumb', b => { b[index] = value; }), 12);
    }
    bad(edited('b2b_crumb', b => { b[3] = 255; b[4] = 255; }), 12);
    bad(edited('b2b_crumb', b => { b.splice(-9, 1); b[8]--; }), 12);
    bad(edited('b2b_ack', b => { b.splice(9, 0, 0); b[8]++; }), 12);
});

test('invalid GPS, mixed accelerometer sentinels and reserved status codes fail closed', () => {
    for (const sats of [0, 1, 3, 65]) bad(edited('primary_v3', b => { b[24] = sats; }));
    for (const [offset, value] of [[0, 900000001], [4, -1800000001], [8, -501], [8, 60001]]) {
        const buffer = Buffer.from(vectors.get('primary_v3').bytes);
        buffer.writeInt32BE(value, offset); bad([...buffer]);
    }
    for (const [offset, value] of [[20, 50001], [22, 36000]]) {
        const buffer = Buffer.from(vectors.get('primary_v3').bytes);
        buffer.writeUInt16BE(value, offset); bad([...buffer]);
    }
    bad(edited('primary_nogps', b => { b[21] = 1; }));
    bad(edited('primary_v3', b => { b[25] = 128; b[26] = 0; }));
    bad(edited('primary_v3', b => { b[34] = 15; }));
    bad(edited('primary_v3', b => { b[34] = 0x70; }));
    const v1 = vectors.get('primary_v3').bytes.slice(0, 35); v1[34] = 2; bad(v1);
});

test('malformed byte-array input never throws or fabricates raw data', () => {
    for (const bytes of [null, '0000', {}, [256], [-1], [0.5], ['1'], [NaN], [Infinity]]) {
        const result = decode(bytes);
        assert(result.errors?.length); assert.equal(result.data.decode_status, 'invalid');
    }
});

function offline(input, success = true) {
    const runner = join(here, 'decode_ttn_uplink.mjs');
    assert(existsSync(runner), 'offline formatter runner is missing');
    let output;
    try {
        output = execFileSync(process.execPath, [runner], { input, encoding: 'utf8', stdio: 'pipe' });
        assert(success, 'invalid offline input should cause nonzero exit status');
    } catch (error) {
        if (success) throw error;
        assert.equal(error.status, 1);
        output = error.stdout;
    }
    return output.trim().split('\n').map(line => JSON.parse(line));
}

test('offline runner decodes raw TTN and direct input with exact formatter parity', () => {
    const direct = { ...vectors.get('primary_v3'), recvTime: receivedAt };
    const bytes = vectors.get('ctt_v2').bytes;
    const ttn = {
        end_device_ids: { device_id: 'host-vector' }, received_at: receivedAt,
        uplink_message: { f_port: 11, f_cnt: 42, frm_payload: Buffer.from(bytes).toString('base64') },
    };
    for (const input of [JSON.stringify([direct, ttn]), `${JSON.stringify(direct)}\n${JSON.stringify(ttn)}\n`]) {
        const results = offline(input);
        assert.equal(results.length, 2);
        assert.deepEqual(results[0].input, direct);
        assert.deepEqual(results[1].input, ttn);
        assert.deepEqual(results[0].decoded, good(direct.bytes));
        assert.deepEqual(results[1].decoded, good(bytes, 11));
    }
});

test('offline runner uses RF receive time instead of later Storage time for CTT age', () => {
    const bytes = edited('ctt_v2', b => { b[15] = 0; b[16] = 5; });
    const input = {
        received_at: '2026-10-05T12:10:00Z',
        uplink_message: { received_at: '2026-10-05T12:00:00.123456789Z',
            f_port: 11, frm_payload: Buffer.from(bytes).toString('base64') },
    };
    const [result] = offline(JSON.stringify(input));
    assert.deepEqual(result.input, input);
    assert.equal(result.decoded.data.detected_at, '2026-10-05T11:55:00.123Z');
    assert.equal(result.decoded.data.raw_hex, Buffer.from(bytes).toString('hex'));
});

test('offline runner falls back to outer receive time only when inner time is absent', () => {
    const bytes = edited('ctt_v2', b => { b[15] = 0; b[16] = 5; });
    const input = {
        received_at: '2026-10-05T12:10:00Z',
        uplink_message: { f_port: 11, frm_payload: Buffer.from(bytes).toString('base64') },
    };
    const [result] = offline(JSON.stringify(input));
    assert.deepEqual(result.input, input);
    assert.equal(result.decoded.data.detected_at, '2026-10-05T12:05:00.000Z');
});

test('offline runner rejects invalid present inner time without replacing it by Storage time', () => {
    const bytes = vectors.get('ctt_v2').bytes;
    for (const inner of [null, '', 'not-a-time', 0, {}, '2026-10-05',
        '2026-10-05T12:00:00', '2026-02-30T12:00:00Z', '2026-10-05T24:00:00Z']) {
        const input = {
            received_at: '2026-10-05T12:10:00Z',
            uplink_message: { received_at: inner, f_port: 11,
                frm_payload: Buffer.from(bytes).toString('base64') },
        };
        const [result] = offline(JSON.stringify(input), false);
        assert.deepEqual(result.input, input);
        assert(result.decoded.errors.some(error => /received_at/.test(error)));
        assert.equal(result.decoded.data.detected_at, undefined);
    }
});

test('offline runner rejects corrupt Base64 and unsupported envelopes while preserving input', () => {
    for (const input of [
        { uplink_message: { f_port: 1, frm_payload: 'AAAA!==' } },
        { uplink_message: { f_port: 1, frm_payload: 'AB==' } },
        { schema: 'stratolink.ttn_uplink_archive.v1', records: [] },
        { fPort: 99, bytes: [1, 2, 3] },
    ]) {
        const [result] = offline(JSON.stringify(input), false);
        assert.deepEqual(result.input, input);
        assert(result.decoded.errors.length);
    }
});
