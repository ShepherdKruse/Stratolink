import { NextResponse } from 'next/server';
import { buildForecastInputForDevice, listForecastDeviceIds } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import {
    acquireForecastLock,
    isBlobStorageConfigured,
    readStoredForecast,
    releaseForecastLock,
    storeForecast,
} from '@/lib/wind/forecastStorage';
import {
    BudgetExceededError,
    budgetRemaining,
    flushBudget,
    getCursor,
    primeBudget,
    setCursor,
} from '@/lib/wind/openMeteoBudget';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;
export const runtime = 'nodejs';

/** Don't recompute a device whose forecast is younger than this — caps the
 *  per-device refresh rate so the fleet stays within the daily call budget.
 *  Bypassed when the last compute was a budget-truncated (partial) reconstruction
 *  that still needs filling in. */
const MIN_RECOMPUTE_MS = 25 * 60 * 1000;
/** Stop the sweep once a window dips below this, so we never start a compute we
 *  can't finish; the persisted cursor resumes from here next tick. */
const MIN_BUDGET_TO_START = 200;

type Result = {
    deviceId: string;
    ok: boolean;
    url?: string;
    error?: string;
    compute_ms?: number;
    skipped?: string;
};

/** Compute + store one device, honoring the freshness skip and call budget. */
async function computeOne(deviceId: string, forecastHours: number, force: boolean): Promise<Result> {
    if (!force) {
        const stored = await readStoredForecast(deviceId);
        if (
            stored &&
            !stored.metadata?.reconstruction_partial &&
            Date.now() - new Date(stored.generated_at).getTime() < MIN_RECOMPUTE_MS
        ) {
            return { deviceId, ok: true, skipped: 'fresh' };
        }
    }
    if (!(await acquireForecastLock(deviceId))) {
        return { deviceId, ok: false, error: 'in-flight' };
    }
    try {
        const input = await buildForecastInputForDevice(deviceId, forecastHours);
        if (!input) return { deviceId, ok: false, error: 'insufficient telemetry' };
        const forecast = await computeMonteCarloForecast(input);
        const url = await storeForecast(deviceId, forecast);
        return { deviceId, ok: true, url: url ?? undefined, compute_ms: forecast.metadata.compute_ms };
    } catch (e) {
        if (e instanceof BudgetExceededError) {
            /* Couldn't afford this compute's winds — defer; the sweep retries this
             * device next tick once the budget window refreshes. */
            return { deviceId, ok: false, error: 'budget' };
        }
        const message = e instanceof Error ? e.message : 'compute failed';
        console.error(`[compute-forecast] ${deviceId} failed: ${message}`);
        return { deviceId, ok: false, error: message };
    } finally {
        await releaseForecastLock(deviceId);
    }
}

export async function GET(req: Request) {
    const secret = process.env.CRON_SECRET;
    if (!secret) {
        return NextResponse.json({ error: 'CRON_SECRET not configured on server' }, { status: 503 });
    }
    if (req.headers.get('authorization') !== `Bearer ${secret}`) {
        return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
    }
    if (!isBlobStorageConfigured()) {
        return NextResponse.json(
            {
                ok: false,
                error: 'BLOB_READ_WRITE_TOKEN not set',
                hint: 'Vercel Dashboard → Storage → Blob → connect to project, then redeploy.',
            },
            { status: 503 },
        );
    }

    const { searchParams } = new URL(req.url);
    const onlyDevice = searchParams.get('device');
    const forecastHours = parseInt(searchParams.get('hours') ?? '24', 10);
    const force = searchParams.get('force') === '1';

    const t0 = Date.now();
    await primeBudget();
    try {
        if (onlyDevice) {
            const r = await computeOne(onlyDevice, forecastHours, force);
            return NextResponse.json({ ok: r.ok, results: [r], elapsed_ms: Date.now() - t0 });
        }

        /* Sweep the fleet round-robin from a persisted cursor — one tick processes
         * as many devices as the budget allows, the next continues where we left
         * off. So work spreads across minute-spaced ticks instead of bursting. */
        const ids = (await listForecastDeviceIds()).sort();
        const results: Result[] = [];
        if (ids.length) {
            const start = getCursor() % ids.length;
            for (let k = 0; k < ids.length; k++) {
                const idx = (start + k) % ids.length;
                const deviceId = ids[idx];
                const rem = budgetRemaining();
                if (rem.day < MIN_BUDGET_TO_START || rem.minute < MIN_BUDGET_TO_START) {
                    setCursor(idx); /* resume here next tick */
                    results.push({ deviceId, ok: false, error: 'budget-deferred' });
                    break;
                }
                const r = await computeOne(deviceId, forecastHours, force);
                results.push(r);
                if (r.error === 'budget') {
                    setCursor(idx); /* ran out mid-compute — retry this device next tick */
                    break;
                }
                setCursor((idx + 1) % ids.length);
            }
        }

        const okCount = results.filter((r) => r.ok).length;
        return NextResponse.json({
            ok: okCount > 0,
            devices: ids.length,
            succeeded: okCount,
            elapsed_ms: Date.now() - t0,
            results,
        });
    } finally {
        await flushBudget();
    }
}
