import { NextResponse } from 'next/server';
import { readStoredForecast, storeForecast } from '@/lib/wind/forecastStorage';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
/** On-demand compute can take several seconds (wind grid fetch + ensemble). */
export const maxDuration = 60;

const STALE_MS = 45 * 60 * 1000;

/**
 * Forecast for a device. Serves the pre-computed forecast from Vercel Blob
 * when one exists (fast path, refreshed by cron). When none is stored yet,
 * computes one on demand so the map always has a prediction to draw — and
 * best-effort caches it for the next reader.
 */
export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const deviceId = searchParams.get('device');
    if (!deviceId) {
        return NextResponse.json({ error: 'device query param required' }, { status: 400 });
    }

    const stored = await readStoredForecast(deviceId);
    if (stored) {
        const ageMs = Date.now() - new Date(stored.generated_at).getTime();
        const stale = ageMs > STALE_MS;
        return NextResponse.json(stored, {
            headers: {
                'Cache-Control': stale
                    ? 'public, max-age=60, s-maxage=120'
                    : 'public, max-age=300, s-maxage=900, stale-while-revalidate=600',
                'X-Forecast-Age-Ms': String(ageMs),
                'X-Forecast-Stale': stale ? '1' : '0',
                'X-Forecast-Source': 'stored',
            },
        });
    }

    /* No stored forecast — compute one now from the device's telemetry. */
    try {
        const input = await buildForecastInputForDevice(deviceId);
        if (!input) {
            return NextResponse.json(
                { error: 'insufficient telemetry to forecast', hint: 'device needs a recent GPS track' },
                { status: 404 },
            );
        }
        const forecast = await computeMonteCarloForecast(input);

        /* Best-effort cache so the next reader (and the cron) skip recompute.
         * Uses Vercel Blob in prod, a local disk cache in dev — either way the
         * next load is served instantly without re-hitting the wind API.
         * Non-fatal, but never silent: a failed store (e.g. a private-access
         * Blob store rejecting public writes) is exactly the kind of bug that
         * hides here, so log it and flag it on the response. */
        let stored = true;
        try {
            await storeForecast(deviceId, forecast);
        } catch (storeErr) {
            stored = false;
            const m = storeErr instanceof Error ? storeErr.message : String(storeErr);
            console.error(`[forecast] failed to cache ${deviceId}: ${m}`);
        }

        return NextResponse.json(forecast, {
            headers: {
                'Cache-Control': 'public, max-age=60, s-maxage=120',
                'X-Forecast-Source': 'on-demand',
                'X-Forecast-Cached': stored ? '1' : '0',
            },
        });
    } catch (e) {
        const message = e instanceof Error ? e.message : 'forecast compute failed';
        return NextResponse.json({ error: message }, { status: 502 });
    }
}
