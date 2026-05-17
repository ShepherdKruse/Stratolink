'use server';

import { registerNewPayload, type RegisterPayloadResult } from '@/lib/ttn/register-payload';

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
