import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase';

export async function POST(request: NextRequest) {
    try {
        const payload = await request.json();
        
        // Extract telemetry data from TTN webhook payload
        const deviceId = payload.end_device_ids?.device_id;
        const receivedAt = payload.received_at;
        const uplinkMessage = payload.uplink_message;
        
        if (!uplinkMessage || !uplinkMessage.frm_payload) {
            return NextResponse.json(
                { error: 'Invalid payload: missing uplink message' },
                { status: 400 }
            );
        }
        
        // Decode base64 payload
        const decodedPayload = Buffer.from(
            uplinkMessage.frm_payload,
            'base64'
        );
        
        // TODO: Parse telemetry data from decoded payload
        // Expected format: GPS coordinates, altitude, battery, etc.
        
        // Insert into Supabase
        const supabase = createClient();
        
        // TODO: Parse telemetry data from decoded payload
        // For now, insert with placeholder values - update when payload format is defined
        const { error } = await supabase
            .from('telemetry')
            .insert({
                device_id: deviceId || 'unknown',
                time: receivedAt || new Date().toISOString(),
                lat: 0, // TODO: Parse from payload
                lon: 0, // TODO: Parse from payload
                altitude_m: 0, // TODO: Parse from payload
                velocity_x: null, // TODO: Parse from payload
                velocity_y: null, // TODO: Parse from payload
            });
        
        if (error) {
            console.error('Supabase insert error:', error);
            return NextResponse.json(
                { error: 'Database insert failed' },
                { status: 500 }
            );
        }
        
        return NextResponse.json({ success: true }, { status: 200 });
        
    } catch (error) {
        console.error('Webhook processing error:', error);
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        );
    }
}
