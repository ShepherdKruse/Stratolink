import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
    authorizeTTNWebhook,
    isProvisionedFleetDevice,
    isExpectedTTNDeliveryDuplicate,
    parseTTNUplinkIdentity,
    readRequestBodyWithinLimit,
} from './webhook-auth.ts';

const secret = '0123456789abcdef0123456789abcdef';

assert.deepEqual(
    authorizeTTNWebhook(`Bearer ${secret}`, secret),
    { ok: true }
);
assert.deepEqual(
    authorizeTTNWebhook(`bearer ${secret}`, secret),
    { ok: true }
);

for (const header of [
    null,
    '',
    secret,
    `Basic ${Buffer.from(`ttn:${secret}`).toString('base64')}`,
    `Bearer ${secret} `,
    `Bearer ${secret}suffix`,
    'Bearer',
    'Bearer two tokens',
]) {
    assert.deepEqual(
        authorizeTTNWebhook(header, secret),
        { ok: false, reason: 'unauthorized' }
    );
}

for (const configured of [undefined, '', 'short']) {
    assert.deepEqual(
        authorizeTTNWebhook(`Bearer ${secret}`, configured),
        { ok: false, reason: 'misconfigured' }
    );
}

assert.equal(isProvisionedFleetDevice({ claim_code: '123456' }), true);
assert.equal(isProvisionedFleetDevice({ claim_code: 'operator-pin' }), true);
assert.equal(isProvisionedFleetDevice({ claim_code: null }), false);
assert.equal(isProvisionedFleetDevice({}), false);
assert.equal(isProvisionedFleetDevice(null), false);
assert.equal(isProvisionedFleetDevice({ claim_code: ' '.repeat(6) }), false);
assert.equal(isProvisionedFleetDevice({ claim_code: 'x'.repeat(129) }), false);

const telemetryDuplicate = {
    code: '23505',
    message:
        'duplicate key value violates unique constraint "idx_telemetry_ttn_delivery"',
};
assert.equal(
    isExpectedTTNDeliveryDuplicate(
        telemetryDuplicate,
        'idx_telemetry_ttn_delivery'
    ),
    true
);
for (const error of [
    null,
    '23505',
    { code: '23505' },
    { code: 23505, message: telemetryDuplicate.message },
    {
        code: '23505',
        message: 'duplicate key value violates unique constraint "devices_pkey"',
    },
    {
        code: '23505',
        message: 'idx_telemetry_ttn_delivery',
    },
    {
        code: '23514',
        message: telemetryDuplicate.message,
    },
]) {
    assert.equal(
        isExpectedTTNDeliveryDuplicate(
            error,
            'idx_telemetry_ttn_delivery'
        ),
        false
    );
}
assert.equal(
    isExpectedTTNDeliveryDuplicate(telemetryDuplicate, 'bad-index-name'),
    false
);

const webhookRoute = readFileSync(
    new URL('../../app/api/ttn-webhook/route.ts', import.meta.url),
    'utf8'
);
assert.equal(webhookRoute.includes("error.code === '23505'"), false);
assert.equal(
    webhookRoute.match(/isExpectedTTNDeliveryDuplicate\(/g)?.length,
    3
);
for (const expectedIndex of [
    'idx_telemetry_ttn_delivery',
    'idx_wildlife_detections_ttn_delivery',
    'idx_b2b_packets_ttn_delivery',
]) {
    assert.equal(webhookRoute.includes(`'${expectedIndex}'`), true);
}

const sessionA = {
    end_device_ids: { device_id: 'stratolink-2', dev_addr: '260cacd0' },
    received_at: '2026-07-25T00:05:13.437315613Z',
    uplink_message: { session_key_id: 'session-a', f_cnt: 0 },
};
assert.deepEqual(parseTTNUplinkIdentity(sessionA), {
    rawDeviceId: 'stratolink-2',
    devAddr: '260CACD0',
    sessionKeyId: 'session-a',
    receivedAt: '2026-07-25T00:05:13.437315613Z',
    frameCounter: 0,
});
assert.deepEqual(parseTTNUplinkIdentity({
    ...sessionA,
    uplink_message: { session_key_id: 'session-b', f_cnt: 0 },
}), {
    rawDeviceId: 'stratolink-2',
    devAddr: '260CACD0',
    sessionKeyId: 'session-b',
    receivedAt: '2026-07-25T00:05:13.437315613Z',
    frameCounter: 0,
});

// This is the exact identity shape observed in current TTN Storage records.
const manualSession = {
    end_device_ids: { device_id: 'stratolink-2', dev_addr: '260CACD0' },
    received_at: '2026-07-25T00:51:52.030951598Z',
    uplink_message: { f_cnt: 5 },
};
assert.deepEqual(parseTTNUplinkIdentity(manualSession), {
    rawDeviceId: 'stratolink-2',
    devAddr: '260CACD0',
    sessionKeyId: null,
    receivedAt: '2026-07-25T00:51:52.030951598Z',
    frameCounter: 5,
});

// A later real uplink may reuse FCnt after a reset. Its server timestamp keeps
// it distinct from an exact retry of the original delivery.
assert.notDeepEqual(
    parseTTNUplinkIdentity(manualSession),
    parseTTNUplinkIdentity({
        ...manualSession,
        received_at: '2026-07-26T00:51:52.030951598Z',
    })
);

for (const invalid of [
    {},
    {
        end_device_ids: {},
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { session_key_id: 's', f_cnt: 1 },
    },
    {
        end_device_ids: { device_id: 'x' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { f_cnt: 1 },
    },
    {
        end_device_ids: { device_id: 'x', dev_addr: '260CACD0' },
        uplink_message: { f_cnt: 1 },
    },
    {
        end_device_ids: { device_id: 'x', dev_addr: 'not-hex!' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { f_cnt: 1 },
    },
    {
        end_device_ids: { device_id: 'x', dev_addr: '260CACD0' },
        received_at: 'not-a-time',
        uplink_message: { f_cnt: 1 },
    },
    {
        end_device_ids: { device_id: 'x' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { session_key_id: 's' },
    },
    {
        end_device_ids: { device_id: 'x' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { session_key_id: 's', f_cnt: -1 },
    },
    {
        end_device_ids: { device_id: 'x' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { session_key_id: 's', f_cnt: 1.5 },
    },
    {
        end_device_ids: { device_id: 'x' },
        received_at: '2026-07-25T00:00:00Z',
        uplink_message: { session_key_id: 's', f_cnt: 0x100000000 },
    },
]) {
    assert.equal(parseTTNUplinkIdentity(invalid), null);
}

async function testBoundedBody(): Promise<void> {
    assert.equal(
        await readRequestBodyWithinLimit(
            new Request('https://example.invalid', { method: 'POST', body: '1234' }),
            4
        ),
        '1234'
    );
    assert.equal(
        await readRequestBodyWithinLimit(
            new Request('https://example.invalid', { method: 'POST', body: '12345' }),
            4
        ),
        null
    );

    const invalidUtf8 = new ReadableStream<Uint8Array>({
        start(controller) {
            controller.enqueue(Uint8Array.from([0xC3, 0x28]));
            controller.close();
        },
    });
    await assert.rejects(
        readRequestBodyWithinLimit(
            new Request('https://example.invalid', {
                method: 'POST',
                body: invalidUtf8,
                // Required by Node when a ReadableStream is the request body.
                duplex: 'half',
            } as RequestInit & { duplex: 'half' }),
            4
        ),
        TypeError
    );
}

testBoundedBody().then(() => {
    console.log(
        'TTN webhook auth, exact-duplicate, manual/OTAA identity, and bounded-body cases passed'
    );
});
