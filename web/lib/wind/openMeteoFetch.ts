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

    const delays = [0, 2000, 5000, 12000];
    let lastRes: Response | null = null;

    for (let attempt = 0; attempt < delays.length; attempt++) {
        if (delays[attempt] > 0) await sleep(delays[attempt]);
        await pace();

        lastRes = await fetch(u.toString(), {
            ...init,
            next: { revalidate: 1800, ...init?.next },
        });

        if (lastRes.ok) return lastRes;
        if (lastRes.status !== 429 && lastRes.status < 500) return lastRes;
    }

    return lastRes!;
}
