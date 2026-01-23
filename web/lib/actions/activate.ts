'use server';

import { createClient } from '@/lib/supabase';

interface ActivateDeviceResult {
    success: boolean;
    message?: string;
    error?: string;
}

export async function activateDevice(
    deviceId: string,
    pin: string,
    launcherName: string,
    latitude: number,
    longitude: number
): Promise<ActivateDeviceResult> {
    try {
        const supabase = createClient();
        
        // Log environment for debugging
        const isDevelopment = process.env.NODE_ENV === 'development' || process.env.NEXT_PUBLIC_DEV_MODE === 'true';
        console.log(`[activateDevice] NODE_ENV: ${process.env.NODE_ENV}, isDevelopment: ${isDevelopment}, deviceId: ${deviceId}`);

        // Step 1: Query for the device
        const { data: device, error: fetchError } = await supabase
            .from('devices')
            .select('*')
            .eq('device_id', deviceId)
            .single();

        // Development mode: Auto-create device if it doesn't exist
        if (fetchError || !device) {
            if (isDevelopment) {
                // In dev mode, use the PIN provided by user as the claim_code
                // This allows testing with any PIN
                const claimCode = pin.length === 6 ? pin : Math.floor(100000 + Math.random() * 900000).toString();
                
                console.log(`[DEV MODE] Auto-creating device ${deviceId} with PIN ${claimCode}`);
                
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
                    console.error('[DEV MODE] Error creating device:', createError);
                    return {
                        success: false,
                        error: `Failed to create test device: ${createError.message}. Make sure the devices table exists.`,
                    };
                }

                if (!newDevice) {
                    return {
                        success: false,
                        error: 'Failed to create test device. Device was not returned after creation.',
                    };
                }

                // Use the newly created device - PIN already matches since we used it
                const createdDevice = newDevice;

                // Update device to flying status
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
                    console.error('[DEV MODE] Error updating device:', updateError);
                    return {
                        success: false,
                        error: `Failed to activate device: ${updateError.message}`,
                    };
                }

                return {
                    success: true,
                    message: 'Launch Confirmed (Test Device Created)',
                };
            }

            return {
                success: false,
                error: 'Device not found. In development mode, devices are auto-created. Check your environment variables.',
            };
        }

        // Step 2: Security Check - Verify PIN matches claim_code
        if (device.claim_code !== pin) {
            // In dev mode, provide helpful error message
            if (isDevelopment) {
                return {
                    success: false,
                    error: `Invalid PIN. Expected: ${device.claim_code}, Got: ${pin}. In dev mode, you can use any PIN for new devices.`,
                };
            }
            return {
                success: false,
                error: 'Invalid PIN',
            };
        }

        // Step 3: State Check - In dev mode, allow re-activation
        if (device.status === 'flying') {
            if (isDevelopment) {
                // In dev mode, allow re-activation by updating the existing record
                console.log(`[DEV MODE] Re-activating device ${deviceId} that was already flying`);
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
                    console.error('[DEV MODE] Error re-activating device:', updateError);
                    return {
                        success: false,
                        error: `Failed to re-activate device: ${updateError.message}`,
                    };
                }

                return {
                    success: true,
                    message: 'Launch Confirmed (Device Re-activated)',
                };
            }
            
            return {
                success: false,
                error: 'Device is already in flight',
            };
        }

        // Step 4: Update device status and launch information
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
            console.error('Error updating device:', updateError);
            return {
                success: false,
                error: 'Failed to activate device',
            };
        }

        // Step 5: Return success
        return {
            success: true,
            message: 'Launch Confirmed',
        };
    } catch (error) {
        console.error('Error in activateDevice:', error);
        return {
            success: false,
            error: 'An unexpected error occurred',
        };
    }
}
