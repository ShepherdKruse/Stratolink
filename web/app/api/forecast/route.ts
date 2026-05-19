import { NextResponse } from 'next/server';
import { readStoredForecast } from '@/lib/wind/forecastStorage';

export const dynamic = 'force-dynamic';

const STALE_MS = 45 * 60 * 1000;

/** Edge-cached read of the latest pre-computed forecast for a device (Vercel Blob). */
export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const deviceId = searchParams.get('device');
    if (!deviceId) {
        return NextResponse.json({ error: 'device query param required' }, { status: 400 });
    }

    const forecast = await readStoredForecast(deviceId);
    if (!forecast) {
        return NextResponse.json(
            { error: 'no cached forecast', hint: 'POST /api/wind-forecast or wait for cron' },
            { status: 404 },
        );
    }

    const ageMs = Date.now() - new Date(forecast.generated_at).getTime();
    const stale = ageMs > STALE_MS;

    return NextResponse.json(forecast, {
        headers: {
            'Cache-Control': stale
                ? 'public, max-age=60, s-maxage=120'
                : 'public, max-age=300, s-maxage=900, stale-while-revalidate=600',
            'X-Forecast-Age-Ms': String(ageMs),
            'X-Forecast-Stale': stale ? '1' : '0',
        },
    });
}
