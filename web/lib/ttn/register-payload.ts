/**
 * Register a new payload on The Things Stack (TTN) + Supabase `devices` row.
 * Issues a one-time launch link (?k=) for field activation without typing the PIN.
 */

import { createServiceRoleClient } from '@/lib/supabase';
import { generateLaunchToken, hashLaunchToken } from '@/lib/launch-token';

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
    activateUrlWithToken: string;
    launchTokenExpiresAt: string;
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

export function publicAppUrl(): string {
    const u = process.env.NEXT_PUBLIC_APP_URL?.trim();
    if (u) return u.replace(/\/$/, '');
    const v = process.env.VERCEL_URL?.trim();
    if (v) return `https://${v.replace(/\/$/, '')}`;
    return 'http://localhost:3000';
}

export type RegisterNewPayloadInput = {
    deviceId?: string;
    joinEui?: string;
    devEui?: string;
};

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
                'Use 3–36 lowercase letters, digits, and hyphens (TTN rules). Example: stratolink-flight-01.',
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
                ' Set TTN_JOIN_EUI or pass joinEui (must match LORAWAN_APP_EUI in firmware secrets.h).',
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

    const launchToken = generateLaunchToken();
    const launchHash = hashLaunchToken(launchToken);
    const launchExpires = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

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
        launch_token_hash: launchHash,
        launch_token_expires_at: launchExpires,
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

    const base = publicAppUrl();
    const activateUrlWithToken = `${base}/activate/${encodeURIComponent(deviceId)}?k=${encodeURIComponent(launchToken)}`;

    const firmwareSnippet = [
        '// Paste into firmware/include/secrets.h (do not commit)',
        `#define LORAWAN_DEV_EUI "${devEui}"`,
        `#define LORAWAN_APP_EUI "${joinEui}"`,
        `#define LORAWAN_APP_KEY "${appKey}"`,
        '',
        `// TTN device_id: ${deviceId}`,
        `// PIN (manual activate): ${claimCode}`,
        `// Launch URL (QR): ${activateUrlWithToken}`,
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
        activateUrlWithToken,
        launchTokenExpiresAt: launchExpires,
    };
}
