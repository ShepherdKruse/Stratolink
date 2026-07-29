'use server';

import { createServiceRoleClient } from '@/lib/supabase';
import { hashLaunchToken, timingSafeEqualHex } from '@/lib/launch-token';

interface ActivateDeviceResult {
    success: boolean;
    message?: string;
    error?: string;
}

function verifyLaunchTokenOnDevice(
    device: {
        claim_code: string | null;
        status: string | null;
        launch_token_hash: string | null;
        launch_token_expires_at: string | null;
    },
    pin: string,
    launchToken?: string | null
): 'pin' | 'token' | false {
    let tokenOk = false;
    if (launchToken && device.launch_token_hash && device.launch_token_expires_at) {
        if (
            device.status === 'storage' &&
            new Date(device.launch_token_expires_at) > new Date()
        ) {
            const h = hashLaunchToken(launchToken);
            tokenOk = timingSafeEqualHex(h, device.launch_token_hash);
        }
    }
    if (tokenOk) return 'token';
    if (device.claim_code && pin.length > 0 && device.claim_code === pin) return 'pin';
    return false;
}

/**
 * @param launchToken — optional `k` query param; when valid, PIN is not required (single-use path clears token).
 */
export async function activateDevice(
    deviceId: string,
    pin: string,
    launcherName: string,
    latitude: number,
    longitude: number,
    launchToken?: string | null
): Promise<ActivateDeviceResult> {
    try {
        const supabase = createServiceRoleClient();

        /* Device creation is a security boundary, not a UI mode. A previous
         * shortcut allowed a NEXT_PUBLIC flag, any Vercel preview environment,
         * or an admin key embedded in deviceId to enable service-role writes.
         * The last form also put the admin secret into a URL/loggable field.
         * Only the actual local development server may auto-create; every
         * deployed build uses the dedicated authenticated admin flows. */
        const isDevelopment = process.env.NODE_ENV === 'development';
        const allowAutoCreate = isDevelopment;

        const { data: device, error: fetchError } = await supabase
            .from('devices')
            .select('*')
            .eq('device_id', deviceId)
            .single();

        if (fetchError || !device) {
            if (allowAutoCreate) {
                const claimCode = pin.length === 6 ? pin : Math.floor(100000 + Math.random() * 900000).toString();

                const { error: createError } = await supabase.from('devices').insert({
                    device_id: deviceId,
                    claim_code: claimCode,
                    status: 'storage',
                });

                if (createError) {
                    return {
                        success: false,
                        error: `Failed to create test device: ${createError.message}`,
                    };
                }

                const { error: updateError } = await supabase
                    .from('devices')
                    .update({
                        status: 'flying',
                        launcher_name: launcherName,
                        launch_lat: latitude,
                        launch_lon: longitude,
                        launched_at: new Date().toISOString(),
                    })
                    .eq('device_id', deviceId);

                if (updateError) {
                    return { success: false, error: `Failed to activate device: ${updateError.message}` };
                }

                return { success: true, message: 'Launch Confirmed (Test Device Created)' };
            }

            return {
                success: false,
                error: `Device not found. Ensure the device was registered before launch.`,
            };
        }

        const auth = verifyLaunchTokenOnDevice(device, pin, launchToken);
        if (!auth) {
            if (isDevelopment) {
                return {
                    success: false,
                    error: `Invalid PIN or launch link. Expected PIN: ${device.claim_code}`,
                };
            }
            return { success: false, error: 'Invalid PIN or launch link' };
        }

        if (device.status === 'flying') {
            if (isDevelopment) {
                const { error: updateError } = await supabase
                    .from('devices')
                    .update({
                        launcher_name: launcherName,
                        launch_lat: latitude,
                        launch_lon: longitude,
                        launched_at: new Date().toISOString(),
                    })
                    .eq('device_id', deviceId);

                if (updateError) {
                    return { success: false, error: `Failed to re-activate device: ${updateError.message}` };
                }
                return { success: true, message: 'Launch Confirmed (Device Re-activated)' };
            }
            return { success: false, error: 'Device is already in flight' };
        }

        const clearLaunch =
            auth === 'token'
                ? { launch_token_hash: null as string | null, launch_token_expires_at: null as string | null }
                : {};

        const { error: updateError } = await supabase
            .from('devices')
            .update({
                status: 'flying',
                launcher_name: launcherName,
                launch_lat: latitude,
                launch_lon: longitude,
                launched_at: new Date().toISOString(),
                ...clearLaunch,
            })
            .eq('device_id', deviceId);

        if (updateError) {
            return { success: false, error: 'Failed to activate device' };
        }

        return { success: true, message: 'Launch Confirmed' };
    } catch (error) {
        console.error('Error in activateDevice:', error);
        return {
            success: false,
            error: error instanceof Error ? error.message : 'An unexpected error occurred',
        };
    }
}
