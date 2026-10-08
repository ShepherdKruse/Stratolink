export type TimelineHistories = readonly (readonly { t: number }[])[];

/** Histories are individually sorted. The fleet does not need a merged copy. */
export function historyRange(histories: TimelineHistories): { start: number; end: number } | null {
    let start = Infinity, end = -Infinity;
    for (const rows of histories) {
        if (!rows.length) continue;
        start = Math.min(start, rows[0].t);
        end = Math.max(end, rows[rows.length - 1].t);
    }
    return start === Infinity ? null : { start, end };
}

/** Strictly previous/next packet time across independently sorted histories. */
export function adjacentPacketTime(histories: TimelineHistories, time: number, direction: 'previous' | 'next'): number | null {
    let result: number | null = null;
    for (const rows of histories) {
        let low = 0, high = rows.length;
        while (low < high) {
            const mid = (low + high) >>> 1;
            if (direction === 'previous' ? rows[mid].t < time : rows[mid].t <= time) low = mid + 1;
            else high = mid;
        }
        const candidate = rows[direction === 'previous' ? low - 1 : low]?.t;
        if (candidate !== undefined) result = result === null ? candidate
            : direction === 'previous' ? Math.max(result, candidate) : Math.min(result, candidate);
    }
    return result;
}
