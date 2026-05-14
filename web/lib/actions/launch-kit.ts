'use server';

import QRCode from 'qrcode';
import { createServiceRoleClient } from '@/lib/supabase';
import { generateLaunchToken, hashLaunchToken, timingSafeEqualHex } from '@/lib/launch-token';
import { publicAppUrl } from '@/lib/ttn/register-payload';

function assertAdmin(adminKey: string): void {
    const expected = process.env.ADMIN_ACTIVATION_KEY;
    if (!expected || adminKey !== expected) {
        throw new Error('Unauthorized');
    }
}

export type LaunchKitRow = {
    device_id: string;
    status: string;
    launch_token_expires_at: string | null;
};

export async function listLaunchKitDevices(adminKey: string): Promise<{ ok: true; devices: LaunchKitRow[] } | { ok: false; error: string }> {
    try {
        assertAdmin(adminKey);
    } catch {
        return { ok: false, error: 'Unauthorized' };
    }
    const supabase = createServiceRoleClient();
    const { data, error } = await supabase
        .from('devices')
        .select('device_id, status, launch_token_expires_at')
        .eq('status', 'storage')
        .order('device_id');

    if (error) {
        return { ok: false, error: error.message };
    }
    return { ok: true, devices: (data || []) as LaunchKitRow[] };
}

export async function rotateLaunchLink(
    adminKey: string,
    deviceId: string
): Promise<
    | { ok: true; activateUrlWithToken: string; launchTokenExpiresAt: string; qrDataUrl: string }
    | { ok: false; error: string }
> {
    try {
        assertAdmin(adminKey);
    } catch {
        return { ok: false, error: 'Unauthorized' };
    }

    const supabase = createServiceRoleClient();
    const { data: row, error: fetchErr } = await supabase
        .from('devices')
        .select('device_id, status')
        .eq('device_id', deviceId)
        .single();

    if (fetchErr || !row) {
        return { ok: false, error: 'Device not found' };
    }
    if (row.status !== 'storage') {
        return { ok: false, error: 'Device must be in storage to issue a launch link' };
    }

    const launchToken = generateLaunchToken();
    const launchHash = hashLaunchToken(launchToken);
    const launchExpires = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

    const { error: upErr } = await supabase
        .from('devices')
        .update({
            launch_token_hash: launchHash,
            launch_token_expires_at: launchExpires,
        })
        .eq('device_id', deviceId);

    if (upErr) {
        return { ok: false, error: upErr.message };
    }

    const base = publicAppUrl();
    const activateUrlWithToken = `${base}/activate/${encodeURIComponent(deviceId)}?k=${encodeURIComponent(launchToken)}`;
    const qrDataUrl = await QRCode.toDataURL(activateUrlWithToken, { width: 320, margin: 2, errorCorrectionLevel: 'M' });

    return {
        ok: true,
        activateUrlWithToken,
        launchTokenExpiresAt: launchExpires,
        qrDataUrl,
    };
}

/** Public: lets activate UI skip PIN when ?k= is valid (storage + not expired). */
export async function peekLaunchToken(deviceId: string, token: string | null): Promise<{ skipPin: boolean }> {
    if (!token || !deviceId) return { skipPin: false };
    let supabase;
    try {
        supabase = createServiceRoleClient();
    } catch {
        return { skipPin: false };
    }
    const { data: device } = await supabase
        .from('devices')
        .select('launch_token_hash, launch_token_expires_at, status')
        .eq('device_id', deviceId)
        .single();

    if (!device?.launch_token_hash || !device.launch_token_expires_at) return { skipPin: false };
    if (device.status !== 'storage') return { skipPin: false };
    if (new Date(device.launch_token_expires_at) <= new Date()) return { skipPin: false };
    const h = hashLaunchToken(token);
    if (!timingSafeEqualHex(h, device.launch_token_hash)) return { skipPin: false };
    return { skipPin: true };
}
