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

        // Step 1: Query for the device
        const { data: device, error: fetchError } = await supabase
            .from('devices')
            .select('*')
            .eq('device_id', deviceId)
            .single();

        // Development mode: Auto-create device if it doesn't exist
        if (fetchError || !device) {
            const isDevelopment = process.env.NODE_ENV === 'development';
            
            if (isDevelopment) {
                // In dev mode, use the PIN provided by user as the claim_code
                // This allows testing with any PIN
                const claimCode = pin.length === 6 ? pin : Math.floor(100000 + Math.random() * 900000).toString();
                
                const { data: newDevice, error: createError } = await supabase
                    .from('devices')
                    .insert({
                        device_id: deviceId,
                        claim_code: claimCode,
                        status: 'storage',
                    })
                    .select()
                    .single();

                if (createError || !newDevice) {
                    return {
                        success: false,
                        error: 'Failed to create test device. Make sure the devices table exists.',
                    };
                }

                // Use the newly created device - PIN already matches since we used it
                const createdDevice = newDevice;

                // State Check
                if (createdDevice.status === 'flying') {
                    return {
                        success: false,
                        error: 'Device is already in flight',
                    };
                }

                // Update device
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

                return {
                    success: true,
                    message: 'Launch Confirmed (Test Device)',
                };
            }

            return {
                success: false,
                error: 'Device not found',
            };
        }

        // Step 2: Security Check - Verify PIN matches claim_code
        if (device.claim_code !== pin) {
            return {
                success: false,
                error: 'Invalid PIN',
            };
        }

        // Step 3: State Check - Ensure device isn't already flying
        if (device.status === 'flying') {
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
