export interface HistoryWindow {
    deviceId: string;
    since: number;
}

interface TimedRow { t: number }
interface Priority { value: boolean }

/** Shared by the fleet and detail views. A failed refresh leaves cached rows intact. */
export function createHistoryLoader<Row extends TimedRow>(
    rowsByDevice: Map<string, Row[]>,
    fetchRows: (deviceId: string, since: number) => Promise<Row[]>,
    concurrency = 4,
) {
    if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error('Invalid history concurrency');
    const windows = new Map<string, { since: number; actualSince: number }>();
    const pending = new Map<string, { since: number; token: symbol; promise: Promise<Row[]>; priority: Priority }>();
    let running = 0;
    const waiting: Array<{ resume: () => void; priority: Priority }> = [];

    async function query(deviceId: string, since: number, priority: Priority) {
        if (running >= concurrency) await new Promise<void>(resume => waiting.push({ resume, priority }));
        else running++;
        try { return await fetchRows(deviceId, since); }
        finally {
            const index = waiting.findIndex(job => job.priority.value);
            const [next] = waiting.splice(Math.max(0, index), 1);
            if (next) next.resume();
            else running--;
        }
    }

    const peek = ({ deviceId, since }: HistoryWindow): Row[] | undefined =>
        windows.get(deviceId)?.since === since ? rowsByDevice.get(deviceId) : undefined;

    function load(window: HistoryWindow, { refresh = false, prioritize = false } = {}): Promise<Row[]> {
        const { deviceId, since } = window;
        const cached = peek(window);
        if (cached !== undefined && !refresh) return Promise.resolve(cached);

        const current = pending.get(deviceId);
        if (current?.since === since) {
            // A selected card gets the next slot without duplicating its fleet query.
            current.priority.value ||= prioritize;
            return current.promise;
        }

        const actualSince = cached === undefined ? since : windows.get(deviceId)!.actualSince;
        const querySince = cached?.length ? cached[cached.length - 1].t : actualSince;
        const token = Symbol();
        const priority = { value: prioritize };
        const request = (async () => {
            let earliest = actualSince;
            let received = await query(deviceId, querySince, priority);
            /* Some registry launch times are later than every stored packet.
             * Keep those real records available without rewriting the registry. */
            if (cached === undefined && received.length === 0 && since > 0) {
                earliest = 0;
                received = await query(deviceId, earliest, priority);
            }

            const byTime = new Map((cached ?? []).map(row => [row.t, row]));
            let changed = cached === undefined;
            for (const row of received) {
                const previous = byTime.get(row.t);
                if (previous && JSON.stringify(previous) === JSON.stringify(row)) continue;
                byTime.set(row.t, row);
                changed = true;
            }
            // Polls include the last packet again. Preserve unchanged histories and their indices.
            const next = changed ? [...byTime.values()].sort((a, b) => a.t - b.t) : cached!;
            if (pending.get(deviceId)?.token === token) {
                rowsByDevice.set(deviceId, next);
                windows.set(deviceId, { since, actualSince: earliest });
            }
            return next;
        })();

        pending.set(deviceId, { since, token, promise: request, priority });
        void request.finally(() => {
            if (pending.get(deviceId)?.promise === request) pending.delete(deviceId);
        }).catch(() => {});
        return request;
    }

    return { load, peek };
}
