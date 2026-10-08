import type { FeatureCollection, LineString } from 'geojson';

export type TimedPosition = { lat: number; lon: number; t: number };
export const TAIL_WINDOW_MS = 24 * 60 * 60_000;

function interpolate(a: TimedPosition, b: TimedPosition, t: number): TimedPosition {
    const fraction = (t - a.t) / (b.t - a.t);
    const delta = ((b.lon - a.lon + 540) % 360) - 180;
    return { t, lat: a.lat + (b.lat - a.lat) * fraction, lon: ((a.lon + delta * fraction + 540) % 360) - 180 };
}

/** Clip to recent GPS history, including the cursor's interpolated position.
 * Never connect across a gap longer than the entire tail window. */
export function flightTail(points: TimedPosition[], cursor: number | null, windowMs = TAIL_WINDOW_MS) {
    const fixes = points.filter(p => Number.isFinite(p.t) && Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180);
    const lastT = fixes.at(-1)?.t;
    const end = lastT == null ? undefined : Math.min(cursor ?? lastT, lastT);
    if (end == null || !Number.isFinite(end) || windowMs <= 0) return { points: [], opacity: 0 };
    const start = end - windowMs;
    const tail: TimedPosition[] = [];
    for (let i = 0; i < fixes.length; i++) {
        const point = fixes[i];
        const previous = fixes[i - 1];
        if (previous && point.t > previous.t && point.t - previous.t <= windowMs) {
            if (previous.t < start && point.t > start && start < end) tail.push(interpolate(previous, point, start));
            if (previous.t < end && point.t > end) tail.push(interpolate(previous, point, end));
        }
        if (point.t >= start && point.t <= end) tail.push(point);
        if (point.t > end) break;
    }
    const last = tail.at(-1);
    return { points: tail, opacity: last ? Math.max(0, 1 - (end - last.t) / windowMs) : 0 };
}

/** Keep a path continuous across the antimeridian without changing its input. */
export function unwrapLngs(coords: Array<[number, number]>): Array<[number, number]> {
    if (coords.length < 2) return coords;
    const out: Array<[number, number]> = [coords[0]];
    let prev = coords[0][0];
    for (let i = 1; i < coords.length; i++) {
        let lon = coords[i][0];
        while (lon - prev > 180) lon -= 360;
        while (lon - prev < -180) lon += 360;
        out.push([lon, coords[i][1]]);
        prev = lon;
    }
    return out;
}

type FleetPath = { deviceId: string; color: string; points: TimedPosition[] };
type TailSource = {
    color: string;
    data: FeatureCollection<LineString, { opacity: number }>;
};

/** A gradient is constant per Mapbox layer; share each palette color across the fleet. */
export function fleetTailSources(paths: FleetPath[], cursor: number | null): TailSource[] {
    const sources = new Map<string, TailSource>();
    for (const path of paths) {
        const tail = flightTail(path.points, cursor);
        if (tail.points.length < 2 || tail.opacity <= 0) continue;
        let source = sources.get(path.color);
        if (!source) {
            source = { color: path.color, data: { type: 'FeatureCollection', features: [] } };
            sources.set(path.color, source);
        }
        source.data.features.push({
            type: 'Feature', id: path.deviceId,
            properties: { opacity: tail.opacity * 0.85 },
            geometry: { type: 'LineString', coordinates: unwrapLngs(tail.points.map(point => [point.lon, point.lat])) },
        });
    }
    return [...sources.values()];
}
