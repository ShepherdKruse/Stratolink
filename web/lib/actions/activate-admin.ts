'use server';

import { createClient } from '@/lib/supabase';

/**
 * Admin-only server action to manually create devices
 * This is secure because it requires ADMIN_ACTIVATION_KEY in environment variables
 * 
 * Usage: Only call this from admin pages or with proper authentication
 */
export async function createDeviceAdmin(
    deviceId: string,
    claimCode: string,
    adminKey: string
): Promise<{ success: boolean; error?: string; message?: string }> {
    try {
        // Verify admin key
        const expectedKey = process.env.ADMIN_ACTIVATION_KEY;
        if (!expectedKey || adminKey !== expectedKey) {
            return {
                success: false,
                error: 'Unauthorized: Invalid admin key',
            };
        }

        const supabase = createClient();

        // Check if device already exists
        const { data: existing } = await supabase
            .from('devices')
            .select('device_id')
            .eq('device_id', deviceId)
            .single();

        if (existing) {
            return {
                success: false,
                error: 'Device already exists',
            };
        }

        // Create device
        const { data: newDevice, error: createError } = await supabase
            .from('devices')
            .insert({
                device_id: deviceId,
                claim_code: claimCode,
                status: 'storage',
            })
            .select()
            .single();

        if (createError) {
            return {
                success: false,
                error: `Failed to create device: ${createError.message}`,
            };
        }

        return {
            success: true,
            message: `Device ${deviceId} created successfully with PIN ${claimCode}`,
        };
    } catch (error) {
        console.error('Error in createDeviceAdmin:', error);
        return {
            success: false,
            error: 'An unexpected error occurred',
        };
    }
}
