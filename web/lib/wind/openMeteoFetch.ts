import {
    BudgetExceededError,
    budgetRemaining,
    callCostForUrl,
    isPrimed,
    markExhausted,
    recordCalls,
} from './openMeteoBudget';

const MIN_GAP_MS = 350;

let lastCallAt = 0;

function sleep(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
}

/** Pace requests to stay under Open-Meteo free-tier limits. */
async function pace(): Promise<void> {
    const now = Date.now();
    const wait = MIN_GAP_MS - (now - lastCallAt);
    if (wait > 0) await sleep(wait);
    lastCallAt = Date.now();
}

/**
 * Fetch Open-Meteo with pacing, retries on 429/5xx, optional API key for higher limits.
 * @see https://open-meteo.com/en/pricing
 */
export async function openMeteoFetch(url: string, init?: RequestInit): Promise<Response> {
    const u = new URL(url);
    const apiKey = process.env.OPEN_METEO_API_KEY;
    if (apiKey) u.searchParams.set('apikey', apiKey);

    /* Free-tier call budget. When a handler has primed the budget, refuse a
     * request that would blow a window — the caller defers (serves cached / 202 /
     * resumes next tick) instead of triggering a hard 400 from Open-Meteo. The
     * weighted cost is ~1 per location (see callCostForUrl), so one grid fetch
     * can be worth many calls. Skipped entirely when not primed (budget off). */
    const cost = callCostForUrl(u.toString());
    if (isPrimed()) {
        const rem = budgetRemaining();
        if (cost > rem.day) throw new BudgetExceededError('day', cost, rem.day);
        if (cost > rem.hour) throw new BudgetExceededError('hour', cost, rem.hour);
        if (cost > rem.minute) throw new BudgetExceededError('minute', cost, rem.minute);
    }

    const delays = [0, 2000, 5000, 12000];
    let lastRes: Response | null = null;

    for (let attempt = 0; attempt < delays.length; attempt++) {
        if (delays[attempt] > 0) await sleep(delays[attempt]);
        await pace();

        lastRes = await fetch(u.toString(), {
            ...init,
            next: { revalidate: 1800, ...init?.next },
        });

        if (lastRes.ok) {
            recordCalls(cost);
            return lastRes;
        }

        /* Open-Meteo reports its OWN limit as 429 (or 400) with a reason like
         * "Daily API request limit exceeded". Their counter is the binding one, so
         * don't retry into it — read the reason, trip the MATCHING window (a daily
         * limit must trip the day breaker, not just the minute, or we'd 429 every
         * tick until midnight), and defer so the caller serves cached / 202 /
         * resumes next tick instead of hammering. */
        if (lastRes.status === 429 || lastRes.status === 400) {
            const body = await lastRes.clone().text().catch(() => '');
            if (lastRes.status === 429 || /limit|exceed/i.test(body)) {
                const scope = /dai|day/i.test(body) ? 'day' : /hour/i.test(body) ? 'hour' : 'minute';
                if (isPrimed()) markExhausted(scope);
                throw new BudgetExceededError(scope, cost, 0);
            }
            return lastRes; /* genuine bad request, not a limit */
        }
        if (lastRes.status < 500) return lastRes;
    }

    return lastRes!;
}
