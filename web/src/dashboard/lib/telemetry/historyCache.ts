export interface HistoryWindow {
    deviceId: string;
    since: number;
}

interface TimedRow { t: number }

/** Shared by the fleet and detail views. A failed refresh leaves cached rows intact. */
export function createHistoryLoader<Row extends TimedRow>(
    rowsByDevice: Map<string, Row[]>,
    fetchRows: (deviceId: string, since: number) => Promise<Row[]>,
) {
    const windows = new Map<string, { since: number; actualSince: number }>();
    const pending = new Map<string, { since: number; token: symbol; promise: Promise<Row[]> }>();

    const peek = ({ deviceId, since }: HistoryWindow): Row[] | undefined =>
        windows.get(deviceId)?.since === since ? rowsByDevice.get(deviceId) : undefined;

    function load(window: HistoryWindow, { refresh = false } = {}): Promise<Row[]> {
        const { deviceId, since } = window;
        const cached = peek(window);
        if (cached !== undefined && !refresh) return Promise.resolve(cached);

        const current = pending.get(deviceId);
        if (current?.since === since) return current.promise;

        const actualSince = cached === undefined ? since : windows.get(deviceId)!.actualSince;
        const querySince = cached?.length ? cached[cached.length - 1].t : actualSince;
        const token = Symbol();
        const request = (async () => {
            let earliest = actualSince;
            let received = await fetchRows(deviceId, querySince);
            /* Some registry launch times are later than every stored packet.
             * Keep those real records available without rewriting the registry. */
            if (cached === undefined && received.length === 0 && since > 0) {
                earliest = 0;
                received = await fetchRows(deviceId, earliest);
            }

            const byTime = new Map((cached ?? []).map(row => [row.t, row]));
            received.forEach(row => byTime.set(row.t, row));
            const next = [...byTime.values()].sort((a, b) => a.t - b.t);
            if (pending.get(deviceId)?.token === token) {
                rowsByDevice.set(deviceId, next);
                windows.set(deviceId, { since, actualSince: earliest });
            }
            return next;
        })();

        pending.set(deviceId, { since, token, promise: request });
        void request.finally(() => {
            if (pending.get(deviceId)?.promise === request) pending.delete(deviceId);
        }).catch(() => {});
        return request;
    }

    return { load, peek };
}
