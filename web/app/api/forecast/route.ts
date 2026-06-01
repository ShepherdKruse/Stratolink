import { NextResponse, after } from 'next/server';
import {
    acquireForecastLock,
    readStoredForecast,
    releaseForecastLock,
    storeForecast,
} from '@/lib/wind/forecastStorage';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
/** The read path returns instantly; the recompute runs in `after()` after the
 *  response, so the function must stay alive long enough to finish it. */
export const maxDuration = 60;

const STALE_MS = 45 * 60 * 1000;

/**
 * Compute + cache a forecast in the background. Runs via `after()` so it
 * executes reliably after the response is sent (a plain non-awaited fetch is
 * killed when a Vercel function returns). The in-flight lock dedupes concurrent
 * polls; an insufficient-telemetry device simply caches nothing.
 */
async function computeAndStore(deviceId: string): Promise<void> {
    if (!(await acquireForecastLock(deviceId))) return; /* already in flight */
    try {
        const input = await buildForecastInputForDevice(deviceId);
        if (!input) return;
        const forecast = await computeMonteCarloForecast(input);
        await storeForecast(deviceId, forecast);
    } catch (e) {
        const m = e instanceof Error ? e.message : String(e);
        console.error(`[forecast] background compute failed for ${deviceId}: ${m}`);
    } finally {
        await releaseForecastLock(deviceId);
    }
}

/**
 * Forecast for a device — READ ONLY. Serves the pre-computed forecast (kept
 * warm by the cron) instantly. The client never blocks on a compute: on a cache
 * miss we return 202 `pending` and recompute in the background (via `after()`,
 * so it runs reliably on Vercel) to self-heal new / cron-missed devices; on a
 * stale cache we serve it now and refresh in the background. The client just
 * polls until the forecast appears.
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
        /* Refresh a stale cache in the background — never block this read. */
        if (stale) after(() => computeAndStore(deviceId));
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

    /* No cache yet — never compute inline. Compute in the background and tell the
     * client to keep polling. (The cron normally keeps caches warm; this
     * self-heals new / cron-missed / on-demand devices, in prod and dev alike.) */
    after(() => computeAndStore(deviceId));

    return NextResponse.json(
        { status: 'pending', device: deviceId },
        { status: 202, headers: { 'Cache-Control': 'no-store', 'X-Forecast-Source': 'pending' } },
    );
}
