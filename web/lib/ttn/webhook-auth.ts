import { createHash, timingSafeEqual } from 'node:crypto';

export type WebhookAuthorization =
    | { ok: true }
    | { ok: false; reason: 'misconfigured' | 'unauthorized' };

export type TTNUplinkIdentity = {
    rawDeviceId: string;
    devAddr: string | null;
    sessionKeyId: string | null;
    receivedAt: string;
    frameCounter: number;
};

type PostgrestLikeError = {
    code?: unknown;
    message?: unknown;
};

/**
 * A 23505 is not automatically an idempotent webhook retry. PostgreSQL uses
 * that code for every unique violation, including unrelated constraints that
 * may be added later. Acknowledge a duplicate only when PostgREST names the
 * exact TTN-delivery index that defines the retry identity for this table.
 */
export function isExpectedTTNDeliveryDuplicate(
    error: unknown,
    expectedIndex: string
): boolean {
    if (
        typeof error !== 'object' ||
        error === null ||
        !/^[a-z][a-z0-9_]{0,62}$/.test(expectedIndex)
    ) {
        return false;
    }
    const candidate = error as PostgrestLikeError;
    return candidate.code === '23505' &&
        typeof candidate.message === 'string' &&
        candidate.message.includes(`"${expectedIndex}"`);
}

/**
 * A public callsign claim creates a reservation row without provisioning TTN
 * credentials. The admin registration paths add a private claim code. Keep
 * that distinction at the ingest boundary so mere row existence cannot turn
 * a reservation into an accepted fleet identity.
 */
export function isProvisionedFleetDevice(
    device: { claim_code?: unknown } | null | undefined
): boolean {
    return typeof device?.claim_code === 'string' &&
        device.claim_code.trim().length > 0 &&
        device.claim_code.length <= 128;
}

const MINIMUM_SECRET_LENGTH = 32;

function digest(value: string): Buffer {
    return createHash('sha256').update(value, 'utf8').digest();
}

/**
 * Authenticate a TTN custom webhook without exposing or directly comparing
 * secret strings. TTN must send:
 *
 *     Authorization: Bearer <TTN_WEBHOOK_SECRET>
 *
 * A missing or weak server secret fails closed. The API keys used to manage
 * TTN are deliberately not accepted here.
 */
export function authorizeTTNWebhook(
    authorizationHeader: string | null,
    configuredSecret: string | undefined
): WebhookAuthorization {
    const expected = configuredSecret?.trim() ?? '';
    if (expected.length < MINIMUM_SECRET_LENGTH) {
        return { ok: false, reason: 'misconfigured' };
    }

    const match = authorizationHeader?.match(/^Bearer ([^\s]+)$/i);
    if (!match) {
        return { ok: false, reason: 'unauthorized' };
    }

    return timingSafeEqual(digest(match[1]), digest(expected))
        ? { ok: true }
        : { ok: false, reason: 'unauthorized' };
}

/**
 * Return the fields that make a TTN delivery unique and auditable.
 *
 * A normal OTAA uplink has session_key_id, but the current StratoLink manual
 * session does not: TTN MQTT and Storage both omit it. DevAddr is therefore
 * required as the session fallback. It is not sufficient for idempotency by
 * itself because a manually provisioned session can reuse both DevAddr and
 * FCntUp after a reset. The database retry key uses TTN's immutable server
 * received_at together with raw device ID and FCntUp. An exact webhook retry
 * or Storage replay retains that timestamp, while a later real uplink does not.
 */
export function parseTTNUplinkIdentity(payload: {
    end_device_ids?: { device_id?: string; dev_addr?: string };
    received_at?: string;
    uplink_message?: { session_key_id?: string; f_cnt?: number };
}): TTNUplinkIdentity | null {
    const rawDeviceId = payload.end_device_ids?.device_id;
    const rawDevAddr = payload.end_device_ids?.dev_addr;
    const rawSessionKeyId = payload.uplink_message?.session_key_id;
    const receivedAt = payload.received_at;
    const frameCounter = payload.uplink_message?.f_cnt;

    const sessionKeyId =
        typeof rawSessionKeyId === 'string' && rawSessionKeyId.length > 0
            ? rawSessionKeyId
            : null;
    const devAddr =
        typeof rawDevAddr === 'string' && /^[0-9A-Fa-f]{8}$/.test(rawDevAddr)
            ? rawDevAddr.toUpperCase()
            : null;

    if (
        typeof rawDeviceId !== 'string' ||
        rawDeviceId.length < 1 ||
        rawDeviceId.length > 64 ||
        typeof receivedAt !== 'string' ||
        receivedAt.length > 64 ||
        !Number.isFinite(Date.parse(receivedAt)) ||
        (rawSessionKeyId !== undefined &&
            (typeof rawSessionKeyId !== 'string' ||
                rawSessionKeyId.length > 4096)) ||
        (rawDevAddr !== undefined && devAddr === null) ||
        (!sessionKeyId && !devAddr) ||
        !Number.isSafeInteger(frameCounter) ||
        frameCounter === undefined ||
        frameCounter < 0 ||
        frameCounter > 0xFFFFFFFF
    ) {
        return null;
    }
    return {
        rawDeviceId,
        devAddr,
        sessionKeyId,
        receivedAt,
        frameCounter,
    };
}

/** Read a request stream without ever buffering more than the accepted size. */
export async function readRequestBodyWithinLimit(
    request: Request,
    maximumBytes: number
): Promise<string | null> {
    if (!request.body) return '';

    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > maximumBytes) {
            await reader.cancel();
            return null;
        }
        chunks.push(value);
    }

    const body = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.byteLength;
    }
    return new TextDecoder('utf-8', { fatal: true }).decode(body);
}
