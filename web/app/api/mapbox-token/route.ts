import { NextResponse } from 'next/server';

export async function GET() {
    // Use NEXT_PUBLIC_MAPBOX_TOKEN (client-side token is safe to expose)
    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || 'pk.eyJ1Ijoic2hlcGtydXNlIiwiYSI6ImNta3E2bHd3NTBzNzYzanB4Zzl5OW14ZDEifQ.j5Co1BLIYPoo0OVU3UqriQ';
    return NextResponse.json({ token });
}
