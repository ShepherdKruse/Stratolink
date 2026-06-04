import { NextResponse } from 'next/server';
import {
    acquireForecastLock,
    readStoredForecast,
    releaseForecastLock,
    storeForecast,
} from '@/lib/wind/forecastStorage';
import { buildForecastInputForDevice } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import { BudgetExceededError, flushBudget, primeBudget } from '@/lib/wind/openMeteoBudget';
import type { StratolinkForecast } from '@/lib/wind/forecastTypes';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
/** On a cold-cache miss we compute inline (the safety net), so the function may
 *  need several seconds. */
export const maxDuration = 60;

const STALE_MS = 45 * 60 * 1000;

/** Compute a forecast for a device (no caching). Null = insufficient telemetry.
 *  Budget-gated via prime/flush so the inline safety net can't blow the free-tier
 *  call limit; throws BudgetExceededError when it can't afford the winds. */
async function computeForecast(deviceId: string): Promise<StratolinkForecast | null> {
    const input = await buildForecastInputForDevice(deviceId);
    if (!input) return null;
    await primeBudget();
    try {
        return await computeMonteCarloForecast(input);
    } finally {
        await flushBudget();
    }
}


/**
 * Forecast for a device.
 *
 * - Fresh cache → served instantly.
 * - Stale cache → served now, refreshed in the background (never blocks).
 * - Cold miss → SAFETY NET: compute inline and return it, so the client always
 *   gets a forecast even if the cache can't persist (e.g. Vercel Blob not
 *   writable). Best-effort cached so warm reads are instant. A concurrent
 *   in-flight compute returns 202 so the client polls instead of duplicating.
 *
 * (Once persistence is confirmed healthy in prod, the cold-miss path can go back
 * to a pure 202 + background compute — see the forecast/hindcast work for #14.)
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
        /* Do NOT recompute-and-overwrite on staleness: the GitHub Actions worker
         * is the sole writer (it builds the GEFS/AIGEFS member ensemble on the
         * runner and refreshes on its cron). A serverless recompute here can't see
         * the member cubes (kept off Blob) and would clobber the worker's ensemble
         * with a parametric GFS forecast. Just serve the stored copy; the worker
         * refreshes it. (Cold miss — no stored forecast at all — still computes
         * below as a bootstrap for a brand-new device.) */
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

    /* Cold miss — safety net. If another request is already computing this
     * device, tell the client to poll rather than duplicate the work. */
    if (!(await acquireForecastLock(deviceId))) {
        return NextResponse.json(
            { status: 'pending', device: deviceId },
            { status: 202, headers: { 'Cache-Control': 'no-store', 'X-Forecast-Source': 'pending' } },
        );
    }
    try {
        const forecast = await computeForecast(deviceId);
        if (!forecast) {
            return NextResponse.json(
                { error: 'insufficient telemetry to forecast', hint: 'device needs a recent GPS track' },
                { status: 404 },
            );
        }
        let cached = true;
        try {
            await storeForecast(deviceId, forecast);
        } catch (e) {
            cached = false;
            console.error(`[forecast] failed to cache ${deviceId}: ${e instanceof Error ? e.message : e}`);
        }
        return NextResponse.json(forecast, {
            headers: {
                'Cache-Control': 'public, max-age=60, s-maxage=120',
                'X-Forecast-Source': 'on-demand',
                'X-Forecast-Cached': cached ? '1' : '0',
            },
        });
    } catch (e) {
        if (e instanceof BudgetExceededError) {
            /* Out of Open-Meteo budget — ask the client to poll; the cron/next
             * read fills the cache once the budget window refreshes. */
            return NextResponse.json(
                { status: 'pending', device: deviceId },
                { status: 202, headers: { 'Cache-Control': 'no-store', 'X-Forecast-Source': 'budget-deferred' } },
            );
        }
        const message = e instanceof Error ? e.message : 'forecast compute failed';
        return NextResponse.json({ error: message }, { status: 502 });
    } finally {
        await releaseForecastLock(deviceId);
    }
}
