#!/usr/bin/env node
// Offline adapter: the wire decoder is exactly the pasteable TTN formatter.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

if (process.argv.includes('--help')) {
    console.log('Usage: node firmware/test/decode_ttn_uplink.mjs [input.json|-]');
    console.log('Input: decodeUplink objects or raw TTN uplinks, as JSON, arrays or NDJSON.');
    console.log('Output: NDJSON {input, decoded}; exit 1 if any packet fails. No network access.');
    process.exit(0);
}

function readInputs(text) {
    if (!text.trim()) throw new Error('Input is empty');
    try {
        const value = JSON.parse(text);
        return Array.isArray(value) ? value : [value];
    } catch (error) {
        if (!(error instanceof SyntaxError)) throw error;
        return text.split(/\r?\n/).filter(line => line.trim()).map(line => JSON.parse(line));
    }
}

function uplinkReceiveTime(input, uplink) {
    if (!Object.prototype.hasOwnProperty.call(uplink, 'received_at')) return input.received_at;
    const value = uplink.received_at;
    // Storage's outer timestamp may be later than RF reception. Never hide a
    // malformed present RF timestamp by substituting that later timestamp.
    const parts = typeof value === 'string' && value.length <= 64 && value.match(
        /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/
    );
    if (!parts || !Number.isFinite(Date.parse(value))) {
        throw new Error('uplink_message.received_at must be a valid RFC3339 timestamp when present');
    }
    const year = Number(parts[1]), month = Number(parts[2]), day = Number(parts[3]);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (day > days[month - 1]) {
        throw new Error('uplink_message.received_at has an invalid calendar date');
    }
    return value;
}

function formatterInput(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input)) {
        throw new Error('Input must be an object');
    }
    if (input.schema === 'stratolink.ttn_uplink_archive.v1') {
        throw new Error('Validate the archive digest with ttn_uplink_archive.py before extracting raw records');
    }
    if ('bytes' in input || 'fPort' in input) return input;
    const uplink = input.uplink_message;
    if (!uplink || typeof uplink !== 'object') {
        throw new Error('Expected {bytes, fPort, recvTime} or a raw TTN uplink_message');
    }
    const encoded = uplink.frm_payload;
    if (typeof encoded !== 'string' ||
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) {
        throw new Error('frm_payload must be canonical Base64');
    }
    const bytes = Buffer.from(encoded, 'base64');
    if (bytes.toString('base64') !== encoded) throw new Error('frm_payload has noncanonical Base64 padding bits');
    return { bytes: [...bytes], fPort: uplink.f_port, recvTime: uplinkReceiveTime(input, uplink) };
}

try {
    if (process.argv.length > 3) throw new Error('Expected at most one input filename; use --help');
    const filename = process.argv[2];
    const inputs = readInputs(readFileSync(!filename || filename === '-' ? 0 : filename, 'utf8'));
    if (!inputs.length) throw new Error('Input contains no uplinks');
    const context = vm.createContext({});
    vm.runInContext(readFileSync(new URL('../../web/public/assets/docs/ttn-uplink-formatter.js', import.meta.url), 'utf8'), context);
    for (const input of inputs) {
        let decoded;
        try {
            decoded = context.decodeUplink(formatterInput(input));
        } catch (error) {
            decoded = { data: { decode_status: 'invalid' }, errors: [error.message] };
        }
        if (decoded.errors?.length) process.exitCode = 1;
        console.log(JSON.stringify({ input, decoded }));
    }
} catch (error) {
    console.error(error.message);
    process.exitCode = 1;
}
