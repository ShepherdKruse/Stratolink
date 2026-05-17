'use server';

import { createServiceRoleClient } from '@/lib/supabase';

/* TTN device_id rules: 3–36 lowercase alphanumeric or hyphens (no leading/trailing or doubled hyphens). */
const TTN_DEVICE_ID_RE = /^[a-z0-9](?:[-]?[a-z0-9]){2,35}$/;

export type ClaimSuccess = {
    ok: true;
    deviceId: string;
    launcherName: string;
};

export type ClaimFailure = {
    ok: false;
    error: string;
};

export type ClaimResult = ClaimSuccess | ClaimFailure;

export async function claimCallsign(rawDeviceId: string, rawName: string, eventCode?: string): Promise<ClaimResult> {
    const required = process.env.CLAIM_EVENT_CODE?.trim();
    if (required && eventCode?.trim() !== required) {
        return { ok: false, error: 'Invalid event code' };
    }

    const deviceId = rawDeviceId.trim().toLowerCase();
    const name = rawName.trim();

    if (!name) return { ok: false, error: 'Please enter your name' };
    if (name.length > 80) return { ok: false, error: 'Name too long (max 80 chars)' };
    if (!TTN_DEVICE_ID_RE.test(deviceId)) {
        return {
            ok: false,
            error: 'Callsign must be 3–36 chars, lowercase letters/digits/hyphens, no spaces (e.g. "stratolink-orion").',
        };
    }

    let supabase;
    try {
        supabase = createServiceRoleClient();
    } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : 'Database unavailable' };
    }

    const { data: existing, error: fetchError } = await supabase
        .from('devices')
        .select('device_id, status, launcher_name')
        .eq('device_id', deviceId)
        .maybeSingle();

    if (fetchError) {
        return { ok: false, error: fetchError.message };
    }

    if (existing) {
        if (existing.status && existing.status !== 'storage') {
            return { ok: false, error: `Callsign "${deviceId}" is already in flight or retired.` };
        }
        if (existing.launcher_name && existing.launcher_name.trim() !== '' && existing.launcher_name !== name) {
            return {
                ok: false,
                error: `Callsign "${deviceId}" already claimed by ${existing.launcher_name}. Pick another.`,
            };
        }
        const { error: updateError } = await supabase
            .from('devices')
            .update({ launcher_name: name, status: 'storage' })
            .eq('device_id', deviceId);
        if (updateError) return { ok: false, error: updateError.message };
        return { ok: true, deviceId, launcherName: name };
    }

    const { error: insertError } = await supabase.from('devices').insert({
        device_id: deviceId,
        status: 'storage',
        launcher_name: name,
    });

    if (insertError) {
        if (insertError.code === '23505') {
            return { ok: false, error: `Callsign "${deviceId}" was just taken. Try another.` };
        }
        return { ok: false, error: insertError.message };
    }

    return { ok: true, deviceId, launcherName: name };
}

export type ClaimedRow = {
    device_id: string;
    launcher_name: string | null;
    has_keys: boolean;
    status: string;
};

export async function listClaims(): Promise<{ ok: true; rows: ClaimedRow[] } | { ok: false; error: string }> {
    let supabase;
    try {
        supabase = createServiceRoleClient();
    } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : 'Database unavailable' };
    }

    const { data, error } = await supabase
        .from('devices')
        .select('device_id, launcher_name, launch_token_hash, status, created_at')
        .not('launcher_name', 'is', null)
        .order('created_at', { ascending: true });

    if (error) return { ok: false, error: error.message };

    const rows: ClaimedRow[] = (data || []).map((d: { device_id: string; launcher_name: string | null; launch_token_hash: string | null; status: string }) => ({
        device_id: d.device_id,
        launcher_name: d.launcher_name,
        has_keys: !!d.launch_token_hash,
        status: d.status,
    }));
    return { ok: true, rows };
}
