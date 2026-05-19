import { NextResponse } from 'next/server';
import { boundsFromPoints, fetchWindGrid } from '@/lib/wind/fetchWindGrid';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const pressureHpa = parseFloat(searchParams.get('pressureHpa') ?? '250');
    const minLat = parseFloat(searchParams.get('minLat') ?? '');
    const maxLat = parseFloat(searchParams.get('maxLat') ?? '');
    const minLon = parseFloat(searchParams.get('minLon') ?? '');
    const maxLon = parseFloat(searchParams.get('maxLon') ?? '');

    if (![minLat, maxLat, minLon, maxLon].every(Number.isFinite)) {
        return NextResponse.json({ error: 'bounds required' }, { status: 400 });
    }

    try {
        const field = await fetchWindGrid(
            { latMin: minLat, latMax: maxLat, lonMin: minLon, lonMax: maxLon },
            pressureHpa,
            1.25,
        );
        return NextResponse.json(field);
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Grid fetch failed';
        return NextResponse.json({ error: message }, { status: 502 });
    }
}
