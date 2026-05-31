import { NextResponse } from 'next/server';
import { readStoredForecast, storeForecast } from '@/lib/wind/forecastStorage';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const STALE_MS = 45 * 60 * 1000;

/** Kick a single-device recompute on a fresh function invocation, without
 *  awaiting — so the read path never blocks on a compute. */
function triggerBackgroundCompute(origin: string, deviceId: string, secret: string): void {
    fetch(`${origin}/api/compute-forecast?device=${encodeURIComponent(deviceId)}`, {
        headers: { Authorization: `Bearer ${secret}` },
    }).catch(() => { /* fire-and-forget */ });
}

/** Local-dev fallback (no CRON_SECRET, so the compute-forecast trigger would
 *  401/503): compute in-process, non-awaited. The long-lived dev server finishes
 *  it and caches the result; the client still only reads. */
function computeInProcess(deviceId: string): void {
    void (async () => {
        try {
            const input = await buildForecastInputForDevice(deviceId);
            if (!input) return;
            const forecast = await computeMonteCarloForecast(input);
            await storeForecast(deviceId, forecast);
        } catch (e) {
            const m = e instanceof Error ? e.message : String(e);
            console.error(`[forecast] background compute failed for ${deviceId}: ${m}`);
        }
    })();
}

/**
 * Forecast for a device — READ ONLY. Serves the pre-computed forecast (kept
 * warm by the cron) instantly. The client never blocks on a compute: on a cache
 * miss we return 202 `pending` and kick a background recompute to self-heal new
 * / cron-missed devices; on a stale cache we serve it now and refresh in the
 * background. The client just polls until the forecast appears.
 */
export async function GET(req: Request) {
    const { searchParams, origin } = new URL(req.url);
    const deviceId = searchParams.get('device');
    if (!deviceId) {
        return NextResponse.json({ error: 'device query param required' }, { status: 400 });
    }
    const secret = process.env.CRON_SECRET;

    const stored = await readStoredForecast(deviceId);
    if (stored) {
        const ageMs = Date.now() - new Date(stored.generated_at).getTime();
        const stale = ageMs > STALE_MS;
        /* Refresh a stale cache in the background — never block this read. */
        if (stale) {
            if (secret) triggerBackgroundCompute(origin, deviceId, secret);
            else computeInProcess(deviceId);
        }
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

    /* No cache yet — never compute inline. Kick a background compute and tell
     * the client to keep polling. (The cron normally keeps caches warm; this
     * self-heals new / cron-missed devices and powers local dev.) */
    if (secret) triggerBackgroundCompute(origin, deviceId, secret);
    else computeInProcess(deviceId);

    return NextResponse.json(
        { status: 'pending', device: deviceId },
        { status: 202, headers: { 'Cache-Control': 'no-store', 'X-Forecast-Source': 'pending' } },
    );
}
