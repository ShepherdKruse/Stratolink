import type { TimedPosition } from './flightTail';

function speed(a: TimedPosition, b: TimedPosition) {
    const rad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
    return 6_371_000 * 2 * Math.asin(Math.min(1, Math.sqrt(h))) / Math.max(1, (b.t - a.t) / 1000);
}

/** Remove invalid fixes and isolated GPS spikes, retaining the telemetry packets. */
export function flightTrack(rows: Array<{ lat: number | null; lon: number | null; t: number }>): TimedPosition[] {
    const fixes = rows.filter((p): p is TimedPosition => p.lat != null && p.lon != null && Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180);
    return fixes.filter((point, index) => {
        const previous = fixes[index - 1], next = fixes[index + 1];
        return !previous || !next || !(speed(previous, point) > 120 && speed(point, next) > 120 && speed(previous, next) < 120);
    });
}
