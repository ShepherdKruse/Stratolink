import { NextResponse } from 'next/server';
import { computeDriftForecast } from '@/lib/wind/driftForecast';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const lat = parseFloat(searchParams.get('lat') ?? '');
    const lon = parseFloat(searchParams.get('lon') ?? '');
    const pressureHpa = parseFloat(searchParams.get('pressureHpa') ?? '250');
    const hours = parseInt(searchParams.get('hours') ?? '24', 10);

    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return NextResponse.json({ error: 'lat and lon required' }, { status: 400 });
    }

    try {
        const points = await computeDriftForecast({
            startLat: lat,
            startLon: lon,
            pressureHpa,
            durationHours: Math.min(72, Math.max(1, hours)),
            stepMinutes: 30,
            refetchEverySteps: 4,
        });

        return NextResponse.json({
            points,
            meta: {
                model: 'Open-Meteo GFS',
                pressureHpa,
                durationHours: hours,
                disclaimer:
                    'Rough drift estimate — balloon moves with layer wind. Not terrain-aware; for planning only.',
            },
        });
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Forecast failed';
        return NextResponse.json({ error: message }, { status: 502 });
    }
}
