import { NextResponse } from 'next/server';
import { computeDriftEnsemble } from '@/lib/wind/driftEnsemble';

/** @deprecated Prefer POST /api/wind-forecast (Monte Carlo + bias correction + ellipses). */
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
        const result = await computeDriftEnsemble({
            startLat: lat,
            startLon: lon,
            pressureHpa,
            durationHours: Math.min(72, Math.max(1, hours)),
            stepMinutes: 30,
            refetchEverySteps: 4,
        });

        return NextResponse.json({
            points: result.points,
            ensemble: result.ensemble,
            cone: result.cone,
            meta: {
                model: 'Open-Meteo GFS',
                pressureHpa,
                durationHours: hours,
                ...result.meta,
                disclaimer:
                    'Ensemble drift: central path uses point-fetched GFS; spread uses ±10% speed, ±15° direction, and four grid-cell wind samples. Planning only.',
            },
        });
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Forecast failed';
        return NextResponse.json({ error: message }, { status: 502 });
    }
}
