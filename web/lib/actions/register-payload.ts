'use server';

import { registerNewPayload, type RegisterPayloadResult } from '@/lib/ttn/register-payload';

/**
 * Registers a device on TTN and in Supabase in one step.
 * Requires `ADMIN_ACTIVATION_KEY` to match (same secret as other admin flows).
 */
export async function registerPayloadAction(
    adminKey: string,
    input: { deviceId?: string; joinEui?: string; devEui?: string }
): Promise<RegisterPayloadResult> {
    const expectedKey = process.env.ADMIN_ACTIVATION_KEY;
    if (!expectedKey || adminKey !== expectedKey) {
        return { ok: false, error: 'Unauthorized', details: 'Invalid admin key.' };
    }
    return registerNewPayload(input);
}
