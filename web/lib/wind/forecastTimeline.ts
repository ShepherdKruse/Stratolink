/** Time scrubber along observed → stale gap → forward forecast paths. */

export type TimelineSegment = 'observed' | 'gap' | 'forecast';

export type ForecastTimeline = {
    tMin: number;
    tMax: number;
    tLastFix: number;
    /** Forecast origin (“implied now” when GPS is stale). */
    tNow: number;
    tForecastEnd: number;
    hasGap: boolean;
};

export type TimelinePosition = {
    lon: number;
    lat: number;
    segment: TimelineSegment;
    /** Hours after tNow when segment is forecast; negative = before now. */
    relHours: number;
};

function lerp(a: number, b: number, f: number): number {
    return a + (b - a) * f;
}

function lerpCoord(
    a: [number, number],
    b: [number, number],
    f: number,
): [number, number] {
    return [lerp(a[0], b[0], f), lerp(a[1], b[1], f)];
}

/** Interpolate [lon, lat] polyline by arc-length fraction 0..1. */
export function coordAlongPath(path: Array<[number, number]>, fraction: number): [number, number] | null {
    if (path.length === 0) return null;
    if (path.length === 1) return path[0];
    const f = Math.max(0, Math.min(1, fraction));
    const segLens: number[] = [];
    let total = 0;
    for (let i = 1; i < path.length; i++) {
        const [lon0, lat0] = path[i - 1];
        const [lon1, lat1] = path[i];
        const cosLat = Math.cos((lat0 * Math.PI) / 180);
        const dx = (lon1 - lon0) * 111.32 * cosLat;
        const dy = (lat1 - lat0) * 111.32;
        const d = Math.hypot(dx, dy);
        segLens.push(d);
        total += d;
    }
    if (total < 1e-6) return path[0];
    let target = f * total;
    for (let i = 0; i < segLens.length; i++) {
        if (target <= segLens[i]) {
            const segF = segLens[i] > 0 ? target / segLens[i] : 0;
            return lerpCoord(path[i], path[i + 1], segF);
        }
        target -= segLens[i];
    }
    return path[path.length - 1];
}

function positionOnTrack(
    track: Array<{ lat: number; lon: number; t: number }>,
    tMs: number,
): [number, number] | null {
    if (track.length === 0) return null;
    if (tMs <= track[0].t) return [track[0].lon, track[0].lat];
    if (tMs >= track[track.length - 1].t) {
        const last = track[track.length - 1];
        return [last.lon, last.lat];
    }
    for (let i = 1; i < track.length; i++) {
        const a = track[i - 1];
        const b = track[i];
        if (tMs >= a.t && tMs <= b.t) {
            const f = b.t === a.t ? 0 : (tMs - a.t) / (b.t - a.t);
            return [lerp(a.lon, b.lon, f), lerp(a.lat, b.lat, f)];
        }
    }
    const last = track[track.length - 1];
    return [last.lon, last.lat];
}

export function buildForecastTimeline(
    observedTrack: Array<{ lat: number; lon: number; t: number }>,
    forecastOriginMs: number,
    forecastHorizonH: number,
    lastFixMs: number,
    hasGap: boolean,
): ForecastTimeline | null {
    if (observedTrack.length < 1 || !Number.isFinite(forecastOriginMs)) return null;
    const tMin = observedTrack[0].t;
    const tLastFix = lastFixMs > 0 ? lastFixMs : observedTrack[observedTrack.length - 1].t;
    const tNow = forecastOriginMs;
    const tForecastEnd = tNow + forecastHorizonH * 3_600_000;
    const tMax = tForecastEnd;
    if (tMax <= tMin) return null;
    return { tMin, tMax, tLastFix, tNow, tForecastEnd, hasGap };
}

export function positionAtTimelineMs(
    tMs: number,
    observedTrack: Array<{ lat: number; lon: number; t: number }>,
    driftPath: Array<[number, number]>,
    nominalPath: Array<[number, number]>,
    timeline: ForecastTimeline,
): TimelinePosition | null {
    const { tLastFix, tNow, hasGap } = timeline;
    const relHours = (tMs - tNow) / 3_600_000;

    if (tMs <= tLastFix) {
        const c = positionOnTrack(observedTrack, tMs);
        if (!c) return null;
        return { lon: c[0], lat: c[1], segment: 'observed', relHours };
    }

    if (hasGap && tMs < tNow && driftPath.length >= 2) {
        const span = tNow - tLastFix;
        const f = span > 0 ? (tMs - tLastFix) / span : 0;
        const c = coordAlongPath(driftPath, f);
        if (!c) return null;
        return { lon: c[0], lat: c[1], segment: 'gap', relHours };
    }

    if (tMs >= tNow && nominalPath.length >= 1) {
        const span = timeline.tForecastEnd - tNow;
        const f = span > 0 ? (tMs - tNow) / span : 0;
        const c = coordAlongPath(nominalPath, f);
        if (!c) return null;
        return { lon: c[0], lat: c[1], segment: 'forecast', relHours };
    }

    if (nominalPath.length >= 1) {
        const c = nominalPath[0];
        return { lon: c[0], lat: c[1], segment: 'forecast', relHours: 0 };
    }

    const c = positionOnTrack(observedTrack, Math.min(tMs, tLastFix));
    if (!c) return null;
    return { lon: c[0], lat: c[1], segment: 'observed', relHours };
}

/** GPS truth at t (only defined on or before last fix). */
export function gpsTruthAt(
    observedTrack: Array<{ lat: number; lon: number; t: number }>,
    tMs: number,
    tLastFix: number,
): { lon: number; lat: number } | null {
    if (tMs > tLastFix) return null;
    const c = positionOnTrack(observedTrack, tMs);
    if (!c) return null;
    return { lon: c[0], lat: c[1] };
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const r = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function formatTimelineUtc(tMs: number): string {
    return new Date(tMs).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'UTC',
    });
}

export function formatTimelineRelLabel(relHours: number, segment: TimelineSegment): string {
    if (segment === 'observed') return 'Observed GPS';
    if (segment === 'gap') {
        const m = Math.round(Math.abs(relHours) * 60);
        if (m < 60) return `Implied drift · ${m}m before now`;
        const h = Math.floor(Math.abs(relHours));
        const rm = Math.round((Math.abs(relHours) - h) * 60);
        return rm > 0 ? `Implied drift · ${h}h ${rm}m before now` : `Implied drift · ${h}h before now`;
    }
    const h = relHours;
    if (h < 0.05) return 'Forecast start (now)';
    const hi = Math.round(h);
    return `Forecast +${hi}h`;
}
