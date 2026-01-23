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
        
        // Check if we're in development mode or have admin override
        // In production, only allow auto-creation if ADMIN_ACTIVATION_KEY is provided and matches
        const hasAdminKey = process.env.ADMIN_ACTIVATION_KEY && 
            typeof deviceId === 'string' && 
            deviceId.includes(process.env.ADMIN_ACTIVATION_KEY);
        
        const isDevelopment = 
            process.env.NODE_ENV === 'development' || 
            process.env.NEXT_PUBLIC_DEV_MODE === 'true' ||
            (process.env.VERCEL_ENV !== 'production' && process.env.VERCEL_ENV !== undefined);
        
        const allowAutoCreate = isDevelopment || hasAdminKey;
        
        console.log(`[activateDevice] NODE_ENV: ${process.env.NODE_ENV}, VERCEL_ENV: ${process.env.VERCEL_ENV}, isDevelopment: ${isDevelopment}, allowAutoCreate: ${allowAutoCreate}, deviceId: ${deviceId}`);

        // Step 1: Query for the device
        const { data: device, error: fetchError } = await supabase
            .from('devices')
            .select('*')
            .eq('device_id', deviceId)
            .single();

        // Development mode or admin: Auto-create device if it doesn't exist
        if (fetchError || !device) {
            console.log(`[activateDevice] Device not found. fetchError:`, fetchError, `allowAutoCreate:`, allowAutoCreate);
            
            if (allowAutoCreate) {
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
                    console.error('[DEV MODE] Error details:', JSON.stringify(createError, null, 2));
                    return {
                        success: false,
                        error: `Failed to create test device: ${createError.message || createError.code || 'Unknown error'}. Check Supabase RLS policies. Error code: ${createError.code || 'N/A'}`,
                    };
                }

                if (!newDevice) {
                    console.error('[DEV MODE] Device was not returned after insert');
                    return {
                        success: false,
                        error: 'Failed to create test device. Device was not returned after creation. Check Supabase RLS policies.',
                    };
                }

                console.log(`[DEV MODE] Device created successfully:`, newDevice);

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
                    console.error('[DEV MODE] Update error details:', JSON.stringify(updateError, null, 2));
                    return {
                        success: false,
                        error: `Failed to activate device: ${updateError.message || updateError.code || 'Unknown error'}. Check Supabase RLS policies. Error code: ${updateError.code || 'N/A'}`,
                    };
                }

                console.log(`[DEV MODE] Device activated successfully`);
                return {
                    success: true,
                    message: 'Launch Confirmed (Test Device Created)',
                };
            }

            // Not in dev mode and no admin key
            console.log(`[activateDevice] Device not found and auto-creation not allowed. NODE_ENV: ${process.env.NODE_ENV}, VERCEL_ENV: ${process.env.VERCEL_ENV}`);
            return {
                success: false,
                error: `Device not found. Please check that you entered the correct Device ID. If you received this device, ensure it was properly registered. Contact support if you believe this is an error.`,
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
