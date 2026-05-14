/**
 * One-step registration: create an OTAA end device on The Things Stack (TTN)
 * and insert a matching row in Supabase `devices` (claim code for launchpad).
 *
 * TTN must push uplinks to your deployed `/api/ttn-webhook` (HTTP integration).
 * Telemetry rows appear when packets arrive; RSSI/SNR come from `rx_metadata`
 * on each uplink (first gateway in the webhook payload).
 */

import { createServiceRoleClient } from '@/lib/supabase';

const TTN_DEVICE_ID_RE = /^[a-z0-9](?:[-]?[a-z0-9]){2,35}$/;

export type RegisterPayloadSuccess = {
    ok: true;
    deviceId: string;
    claimCode: string;
    devEui: string;
    joinEui: string;
    appKey: string;
    firmwareSnippet: string;
    ttnDeviceUrl: string;
};

export type RegisterPayloadFailure = {
    ok: false;
    error: string;
    details?: string;
};

export type RegisterPayloadResult = RegisterPayloadSuccess | RegisterPayloadFailure;

function randomHex(byteLength: number): string {
    const buf = new Uint8Array(byteLength);
    crypto.getRandomValues(buf);
    return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
}

function normalizeHex16(label: string, value: string): string {
    const s = value.replace(/\s+/g, '').toLowerCase();
    if (!/^[0-9a-f]{16}$/.test(s)) {
        throw new Error(`${label} must be exactly 16 hexadecimal characters (8 bytes)`);
    }
    return s;
}

function defaultDeviceId(): string {
    return `sl-${randomHex(4)}`;
}

function generateClaimCode(): string {
    const n = 100000 + Math.floor(Math.random() * 900000);
    return String(n);
}

function ttsApiBase(clusterUrl: string): string {
    const u = clusterUrl.replace(/\/$/, '');
    if (!u.startsWith('http')) {
        return `https://${u}/api/v3`;
    }
    return `${u}/api/v3`;
}

/** Hostname only, for TTS `*_server_address` fields (no scheme, no path). */
function clusterHostOnly(clusterUrl: string): string {
    const u = clusterUrl.replace(/\/$/, '');
    try {
        const withProto = u.startsWith('http') ? u : `https://${u}`;
        return new URL(withProto).hostname;
    } catch {
        return u.replace(/^https?:\/\//i, '').split('/')[0] || u;
    }
}

function ttsConsoleDeviceUrl(clusterUrl: string, applicationId: string, deviceId: string): string {
    const u = clusterUrl.replace(/\/$/, '');
    const origin = u.startsWith('http') ? new URL(u).origin : `https://${u}`;
    return `${origin}/applications/${encodeURIComponent(applicationId)}/devices/${encodeURIComponent(deviceId)}`;
}

async function ttsDeleteDevice(
    apiBase: string,
    applicationId: string,
    deviceId: string,
    apiKey: string
): Promise<void> {
    const url = `${apiBase}/applications/${encodeURIComponent(applicationId)}/devices/${encodeURIComponent(deviceId)}`;
    await fetch(url, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${apiKey}` },
    });
}

async function ttsPutDevice(
    apiBase: string,
    applicationId: string,
    deviceId: string,
    apiKey: string,
    body: Record<string, unknown>
): Promise<{ ok: true } | { ok: false; status: number; text: string }> {
    const url = `${apiBase}/applications/${encodeURIComponent(applicationId)}/devices/${encodeURIComponent(deviceId)}`;
    const res = await fetch(url, {
        method: 'PUT',
        headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const text = await res.text();
        return { ok: false, status: res.status, text };
    }
    return { ok: true };
}

export type RegisterNewPayloadInput = {
    /** TTN `device_id` (and Supabase `devices.device_id`). Lowercase letters, digits, hyphens; 3–36 chars. */
    deviceId?: string;
    /** Join EUI / LoRaWAN “AppEUI” (16 hex). Defaults to `TTN_JOIN_EUI` env. */
    joinEui?: string;
    /** DevEUI (16 hex). If omitted, a random DevEUI is generated (flash it or use a chip-stored EUI if you have one). */
    devEui?: string;
};

/**
 * Register a new payload on TTN and in Supabase. Requires server env:
 * - TTN_STACK_HOST (e.g. https://nam1.cloud.thethings.network)
 * - TTN_APPLICATION_ID
 * - TTN_API_KEY (NNSXS… with rights to create devices in that application)
 * - TTN_JOIN_EUI (16 hex) unless `joinEui` is passed in the input
 * - TTN_FREQUENCY_PLAN_ID (default US_902_928_FSB2 if unset)
 * - SUPABASE_SERVICE_ROLE_KEY, NEXT_PUBLIC_SUPABASE_URL
 */
export async function registerNewPayload(input: RegisterNewPayloadInput): Promise<RegisterPayloadResult> {
    const clusterUrl = process.env.TTN_STACK_HOST?.trim();
    const applicationId = process.env.TTN_APPLICATION_ID?.trim();
    const apiKey = process.env.TTN_API_KEY?.trim();
    const defaultJoin = process.env.TTN_JOIN_EUI?.trim();
    const frequencyPlanId = process.env.TTN_FREQUENCY_PLAN_ID?.trim() || 'US_902_928_FSB2';

    if (!clusterUrl || !applicationId || !apiKey) {
        return {
            ok: false,
            error: 'Missing TTN configuration',
            details: 'Set TTN_STACK_HOST, TTN_APPLICATION_ID, and TTN_API_KEY on the server.',
        };
    }

    let deviceId = (input.deviceId || defaultDeviceId()).trim().toLowerCase();
    if (!TTN_DEVICE_ID_RE.test(deviceId)) {
        return {
            ok: false,
            error: 'Invalid device_id',
            details:
                'Use 3–36 lowercase letters, digits, and non-leading hyphens (TTN device ID rules). Example: stratolink-flight-01.',
        };
    }

    let joinEui: string;
    try {
        joinEui = normalizeHex16('joinEui', input.joinEui || defaultJoin || '');
    } catch (e) {
        return {
            ok: false,
            error: 'Invalid or missing Join EUI',
            details:
                (e instanceof Error ? e.message : String(e)) +
                ' Set TTN_JOIN_EUI in the environment or pass joinEui (must match LORAWAN_APP_EUI in firmware secrets.h).',
        };
    }

    let devEui: string;
    try {
        devEui = input.devEui ? normalizeHex16('devEui', input.devEui) : randomHex(8);
    } catch (e) {
        return {
            ok: false,
            error: 'Invalid DevEUI',
            details: e instanceof Error ? e.message : String(e),
        };
    }

    const appKey = randomHex(16);
    const claimCode = generateClaimCode();
    const apiBase = ttsApiBase(clusterUrl);
    const stackHost = clusterHostOnly(clusterUrl);

    const endDeviceBody = {
        end_device: {
            ids: {
                device_id: deviceId,
                application_ids: { application_id: applicationId },
                join_eui: joinEui,
                dev_eui: devEui,
            },
            name: `Stratolink ${deviceId}`,
            network_server_address: stackHost,
            application_server_address: stackHost,
            join_server_address: stackHost,
            supports_join: true,
            root_keys: {
                app_key: { key: appKey },
            },
            lorawan_version: 'MAC_V1_0_3',
            lorawan_phy_version: 'PHY_V1_0_3_REV_A',
            frequency_plan_id: frequencyPlanId,
        },
    };

    const put = await ttsPutDevice(apiBase, applicationId, deviceId, apiKey, endDeviceBody);
    if (!put.ok) {
        return {
            ok: false,
            error: `TTN rejected device registration (HTTP ${put.status})`,
            details: put.text.slice(0, 2000),
        };
    }

    const supabase = createServiceRoleClient();
    const { error: insertError } = await supabase.from('devices').insert({
        device_id: deviceId,
        claim_code: claimCode,
        status: 'storage',
    });

    if (insertError) {
        try {
            await ttsDeleteDevice(apiBase, applicationId, deviceId, apiKey);
        } catch {
            /* best-effort rollback */
        }
        return {
            ok: false,
            error: 'Supabase insert failed after TTN registration',
            details: insertError.message,
        };
    }

    const firmwareSnippet = [
        '// Paste into firmware/include/secrets.h (do not commit)',
        `#define LORAWAN_DEV_EUI "${devEui}"`,
        `#define LORAWAN_APP_EUI "${joinEui}"`,
        `#define LORAWAN_APP_KEY "${appKey}"`,
        '',
        `// TTN device_id / dashboard: ${deviceId}`,
        `// Launch PIN (claim_code): ${claimCode}`,
    ].join('\n');

    return {
        ok: true,
        deviceId,
        claimCode,
        devEui,
        joinEui,
        appKey,
        firmwareSnippet,
        ttnDeviceUrl: ttsConsoleDeviceUrl(clusterUrl, applicationId, deviceId),
    };
}
