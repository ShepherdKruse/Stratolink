import type { TimedPosition } from './flightTail';

export function cleanReconstructedTrack(raw: unknown): TimedPosition[] {
    if (!Array.isArray(raw)) return [];
    const track: TimedPosition[] = [];
    for (const point of raw) {
        if (!point || typeof point !== 'object') continue;
        const { lon, lat } = point;
        const t = typeof point.time_utc === 'string' ? Date.parse(point.time_utc) : NaN;
        if (typeof lon === 'number' && typeof lat === 'number' && Number.isFinite(lon)
            && Number.isFinite(lat) && Math.abs(lat) <= 90 && Number.isFinite(t)) {
            track.push({ lon: ((lon + 180) % 360 + 360) % 360 - 180, lat, t });
        }
    }
    return track.sort((a, b) => a.t - b.t);
}

/** Use the stored wind reconstruction between recorded fixes, never beyond them. */
export function reconstructedFlightTrack(fixes: TimedPosition[], reconstruction: TimedPosition[]): TimedPosition[] {
    if (fixes.length < 2 || reconstruction.length < 2) return fixes;
    const first = fixes[0].t, last = fixes[fixes.length - 1].t;
    const points = new Map(reconstruction.filter(point => point.t >= first && point.t <= last).map(point => [point.t, point]));
    for (const fix of fixes) points.set(fix.t, fix);
    return [...points.values()].sort((a, b) => a.t - b.t);
}
