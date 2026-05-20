import type { ForecastGpsFix } from './forecastTypes';
import { STALE_GPS_THRESHOLD_H } from './staleGpsExtrapolation';
import { splitTrackSegments } from './trackSegments';

const EPS = 0.0008;
const FREEZE_MIN_MS = 18 * 60_000;
const GAP_MIN_MS = STALE_GPS_THRESHOLD_H * 3_600_000;
const MAX_GAP_H = 72;
const MAX_GAPS_TO_INFER = 12;

export type TrackPoint = {
    lat: number;
    lon: number;
    t: number;
    alt_m?: number;
};

export type InferredGap = {
    kind: 'freeze' | 'interval';
    startFix: ForecastGpsFix;
    endFix: ForecastGpsFix;
    gapHours: number;
};

function toFix(p: TrackPoint): ForecastGpsFix {
    return {
        lat: p.lat,
        lon: p.lon,
        time_utc: new Date(p.t).toISOString(),
        alt_m: p.alt_m,
    };
}

function samePosition(a: TrackPoint, b: TrackPoint): boolean {
    return Math.abs(a.lat - b.lat) < EPS && Math.abs(a.lon - b.lon) < EPS;
}

/** GPS freeze (locked coords) and long intervals between fixes. */
export function detectInferredGaps(track: TrackPoint[]): InferredGap[] {
    if (track.length < 2) return [];

    const gaps: InferredGap[] = [];
    const covered = new Set<string>();

    const mark = (startMs: number, endMs: number) => {
        covered.add(`${startMs}-${endMs}`);
    };
    const isCovered = (startMs: number, endMs: number) => covered.has(`${startMs}-${endMs}`);

    const segs = splitTrackSegments(track.map((p) => ({ lat: p.lat, lon: p.lon, t: p.t })));
    if (segs.freezeDrift.length >= 2 && segs.resumed.length > 0 && segs.observed.length > 0) {
        const start = segs.observed[segs.observed.length - 1];
        const end = segs.resumed[0];
        const startMs = start.t;
        const endMs = end.t;
        const gapHours = Math.min(MAX_GAP_H, (endMs - startMs) / 3_600_000);
        if (gapHours >= STALE_GPS_THRESHOLD_H) {
            gaps.push({
                kind: 'freeze',
                startFix: toFix(start),
                endFix: toFix(end),
                gapHours,
            });
            mark(startMs, endMs);
        }
    }

    for (let i = 1; i < track.length; i++) {
        const prev = track[i - 1];
        const cur = track[i];
        const startMs = prev.t;
        const endMs = cur.t;
        if (isCovered(startMs, endMs)) continue;

        const dtMs = endMs - startMs;
        if (dtMs < GAP_MIN_MS) continue;
        if (samePosition(prev, cur)) continue;

        const gapHours = Math.min(MAX_GAP_H, dtMs / 3_600_000);
        gaps.push({
            kind: 'interval',
            startFix: toFix(prev),
            endFix: toFix(cur),
            gapHours,
        });
        mark(startMs, endMs);
    }

    gaps.sort((a, b) => b.gapHours - a.gapHours);
    return gaps.slice(0, MAX_GAPS_TO_INFER);
}

export function fixesBeforeAnchor(allFixes: ForecastGpsFix[], anchorUtc: string): ForecastGpsFix[] {
    const anchorMs = new Date(anchorUtc).getTime();
    const history = allFixes.filter((f) => new Date(f.time_utc).getTime() <= anchorMs + 1000);
    if (history.length >= 2) return history;
    return allFixes.slice(0, Math.min(2, allFixes.length));
}
