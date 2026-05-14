import { NextRequest, NextResponse } from 'next/server';
import { registerNewPayload } from '@/lib/ttn/register-payload';

/**
 * POST /api/admin/register-payload
 *
 * Headers: Authorization: Bearer <ADMIN_ACTIVATION_KEY>
 * Body JSON: { "deviceId"?: string, "joinEui"?: string, "devEui"?: string }
 *
 * Creates an OTAA end device on TTN and a `devices` row in Supabase with a claim PIN.
 */
export async function POST(request: NextRequest) {
    const auth = request.headers.get('authorization');
    const token = auth?.startsWith('Bearer ') ? auth.slice(7).trim() : '';
    const expected = process.env.ADMIN_ACTIVATION_KEY;

    if (!expected || token !== expected) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    let body: { deviceId?: string; joinEui?: string; devEui?: string } = {};
    try {
        body = await request.json();
    } catch {
        return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
    }

    const result = await registerNewPayload(body);
    if (!result.ok) {
        const status = result.error.includes('TTN rejected')
            ? 502
            : result.error.includes('Supabase')
              ? 500
              : 400;
        return NextResponse.json({ error: result.error, details: result.details }, { status });
    }

    return NextResponse.json(result, { status: 201 });
}
