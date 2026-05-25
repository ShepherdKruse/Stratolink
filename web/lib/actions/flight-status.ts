'use server';

import { createServiceRoleClient } from '@/lib/supabase';

/**
 * Admin-gated flight lifecycle actions.
 *
 * A flight's lifecycle in the `devices` table is: storage → flying → landed
 * (→ retired). Mission Control shows `flying` devices; the Mission Archive
 * shows `landed`/`retired` ones. There was no UI to flip a device out of
 * `flying` when it lands, so completed missions never reached the archive —
 * these actions close that gap.
 *
 * Writes use the service-role client and require ADMIN_ACTIVATION_KEY, since
 * the public dashboard must never be able to change a device's status.
 */

function assertAdmin(adminKey: string): void {
    const expected = process.env.ADMIN_ACTIVATION_KEY;
    if (!expected || adminKey !== expected) {
        throw new Error('Unauthorized');
    }
}

export type FlightStatus = 'flying' | 'landed' | 'retired';
/* `storage` is intentionally excluded — a launched device should never be
 * moved back to a pre-launch state through this UI. */
const ALLOWED: FlightStatus[] = ['flying', 'landed', 'retired'];

export type FlightRow = {
    device_id: string;
    status: string;
    launcher_name: string | null;
    launched_at: string | null;
};

export async function listFlightDevices(
    adminKey: string,
): Promise<{ ok: true; devices: FlightRow[] } | { ok: false; error: string }> {
    try {
        assertAdmin(adminKey);
    } catch {
        return { ok: false, error: 'Unauthorized' };
    }
    const supabase = createServiceRoleClient();
    const { data, error } = await supabase
        .from('devices')
        .select('device_id, status, launcher_name, launched_at')
        .in('status', ALLOWED)
        .order('launched_at', { ascending: false });

    if (error) {
        return { ok: false, error: error.message };
    }
    return { ok: true, devices: (data || []) as FlightRow[] };
}

export async function setFlightStatus(
    adminKey: string,
    deviceId: string,
    status: FlightStatus,
): Promise<{ ok: true; status: FlightStatus } | { ok: false; error: string }> {
    try {
        assertAdmin(adminKey);
    } catch {
        return { ok: false, error: 'Unauthorized' };
    }
    if (!ALLOWED.includes(status)) {
        return { ok: false, error: 'Invalid status' };
    }

    const supabase = createServiceRoleClient();
    const { data: row, error: fetchErr } = await supabase
        .from('devices')
        .select('device_id, status, launched_at')
        .eq('device_id', deviceId)
        .single();

    if (fetchErr || !row) {
        return { ok: false, error: 'Device not found' };
    }

    const { error: upErr } = await supabase
        .from('devices')
        .update({ status })
        .eq('device_id', deviceId);

    if (upErr) {
        return { ok: false, error: upErr.message };
    }
    return { ok: true, status };
}
