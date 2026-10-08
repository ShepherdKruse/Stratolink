export interface ForecastData {
    nominal_path?: unknown;
    ensemble?: unknown[];
    ellipses?: Array<{ e50?: { polygon?: unknown }; e90?: { polygon?: unknown } }>;
    forecast_origin?: { time_utc?: string };
    forecast_horizon_h?: unknown;
    observed?: { reconstructed_path?: unknown; reconstructed_track?: unknown };
    predicted_hindcast?: { path?: unknown };
    stale_gps?: { coverage_limited?: unknown };
    divergence?: unknown;
    generated_at?: unknown;
}
export type ForecastResponse = { status: number; data: ForecastData | null };
type ForecastView = 'full' | 'path';
type FetchForecast = (id: string, signal: AbortSignal, view: ForecastView) => Promise<ForecastResponse>;
type Subscriber = { resolve: (result: ForecastResponse) => void; reject: (error: unknown) => void; cleanup: () => void };
type Job = { id: string; key: string; view: ForecastView; controller: AbortController; subscribers: Set<Subscriber> };

/** Share public forecast reads, bound their concurrency and cancel abandoned work. */
export function createForecastRequests(fetchForecast: FetchForecast, now = Date.now) {
    const pending = new Map<string, Job>();
    const queue: Job[] = [];
    const cache = new Map<string, { result: ForecastResponse; until: number }>();
    let running = 0;

    function drain() {
        while (running < 4 && queue.length) {
            const job = queue.shift()!;
            if (!job.subscribers.size) continue;
            running++;
            void (async () => {
                try {
                    const result = await fetchForecast(job.id, job.controller.signal, job.view);
                    if (job.subscribers.size && pending.get(job.key) === job && ((result.status >= 200 && result.status < 300) || result.status === 404)) {
                        cache.delete(job.key);
                        cache.set(job.key, { result, until: now() + (result.status === 202 ? 8000 : 300_000) });
                        while (cache.size > 64) cache.delete(cache.keys().next().value!);
                    }
                    for (const subscriber of job.subscribers) { subscriber.cleanup(); subscriber.resolve(result); }
                } catch (error) {
                    for (const subscriber of job.subscribers) { subscriber.cleanup(); subscriber.reject(error); }
                } finally {
                    job.subscribers.clear();
                    if (pending.get(job.key) === job) pending.delete(job.key);
                    running--;
                    drain();
                }
            })();
        }
    }

    function load(id: string, signal: AbortSignal, prioritize = false, view: ForecastView = 'full'): Promise<ForecastResponse> {
        if (signal.aborted) return Promise.reject(new DOMException('Forecast cancelled', 'AbortError'));
        const key = `${view}:${id}`;
        const cached = cache.get(key);
        if (cached && cached.until > now()) return Promise.resolve(cached.result);
        cache.delete(key);
        let job = pending.get(key);
        if (!job) {
            job = { id, key, view, controller: new AbortController(), subscribers: new Set() };
            pending.set(key, job);
            queue.push(job);
        }
        if (prioritize) {
            const index = queue.indexOf(job);
            if (index > 0) queue.unshift(queue.splice(index, 1)[0]);
        }
        const request = job;
        return new Promise((resolve, reject) => {
            const abort = () => {
                request.subscribers.delete(subscriber);
                subscriber.cleanup();
                reject(new DOMException('Forecast cancelled', 'AbortError'));
                if (!request.subscribers.size) {
                    request.controller.abort();
                    if (pending.get(key) === request) pending.delete(key);
                    const index = queue.indexOf(request);
                    if (index >= 0) queue.splice(index, 1);
                }
            };
            const subscriber: Subscriber = { resolve, reject, cleanup: () => signal.removeEventListener('abort', abort) };
            request.subscribers.add(subscriber);
            signal.addEventListener('abort', abort, { once: true });
            drain();
        });
    }
    function watch(id: string, onResult: (result: ForecastResponse) => void, prioritize = false, view: ForecastView = 'full') {
        const controller = new AbortController();
        let timer: ReturnType<typeof setTimeout> | undefined;
        let fastPolls = 0;
        async function poll() {
            let result: ForecastResponse;
            try { result = await load(id, controller.signal, prioritize, view); }
            catch { result = { status: 0, data: null }; }
            if (controller.signal.aborted) return;
            const delay = result.status === 202 && fastPolls++ < 15 ? 8000 : 300_000;
            if (result.status !== 202) fastPolls = 0;
            onResult(result);
            timer = setTimeout(poll, delay);
        }
        void poll();
        return () => { controller.abort(); clearTimeout(timer); };
    }
    return { load, watch };
}

export const forecastRequests = createForecastRequests(async (id, signal, view) => {
    const response = await fetch(`/api/forecast?device=${encodeURIComponent(id)}${view === 'path' ? '&view=path' : ''}`, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
    });
    return { status: response.status, data: response.ok && response.status !== 202 ? await response.json() : null };
});
