import type { TelemetryRow } from '@/components/dashboard-v2/atoms';

export type FlightEventKind = 'launch' | 'float' | 'gps_lost' | 'coast' | 'landfall' | 'now';

export type FlightEvent = {
    kind: FlightEventKind;
    label: string;
    t: number;
};

export type NarrativeGapSegment = {
    type: 'gap';
    t0: number;
    t1: number;
    label: string;
    widthFrac: number;
};

export type NarrativeSignalSegment = {
    type: 'signal';
    t0: number;
    t1: number;
    widthFrac: number;
};

export type NarrativeSegment = NarrativeGapSegment | NarrativeSignalSegment;

export type FlightNarrative = {
    events: FlightEvent[];
    segments: NarrativeSegment[];
    tStart: number;
    tEnd: number;
    packetEndT: number;
    timeToFraction: (t: number) => number;
    fractionToTime: (f: number) => number;
};

const GAP_LABEL_MS = 2 * 3_600_000;
const GAP_RAIL_FRAC = 0.045;
const MIN_SIGNAL_FRAC = 0.06;
const FLOAT_ALT_LO = 8500;
const FLOAT_ALT_HI = 12000;

const EVENT_ORDER: FlightEventKind[] = ['launch', 'float', 'gps_lost', 'coast', 'landfall', 'now'];

function hasGps(r: TelemetryRow): boolean {
    return r.lat != null && r.lon != null;
}

function fmtGapLabel(ms: number): string {
    const h = Math.round(ms / 3_600_000);
    if (h >= 48) return `${Math.round(h / 24)}d · no signal`;
    if (h >= 1) return `${h}h · no signal`;
    const m = Math.max(1, Math.round(ms / 60_000));
    return `${m}m · no signal`;
}

/** Auto-detect narrative milestones from telemetry + device metadata. */
export function detectFlightEvents(
    rows: TelemetryRow[],
    opts?: { launchedAt?: number | null },
): FlightEvent[] {
    if (rows.length === 0) return [];

    const launchT = opts?.launchedAt ?? rows[0].t;
    const out: FlightEvent[] = [{ kind: 'launch', label: 'LAUNCH', t: launchT }];

    const floatRow = rows.find(
        (r) =>
            r.presAlt != null &&
            r.presAlt >= FLOAT_ALT_LO &&
            r.presAlt <= FLOAT_ALT_HI &&
            r.t >= launchT + 15 * 60_000,
    );
    if (floatRow) out.push({ kind: 'float', label: 'FLOAT', t: floatRow.t });

    for (let i = 1; i < rows.length; i++) {
        const dt = rows[i].t - rows[i - 1].t;
        if (dt >= GAP_LABEL_MS) {
            const hadGpsBefore = rows.slice(0, i).some(hasGps);
            if (hadGpsBefore && !out.some((e) => e.kind === 'gps_lost')) {
                out.push({ kind: 'gps_lost', label: 'GPS LOST', t: rows[i - 1].t });
            }
            break;
        }
    }

    let wasFloating = false;
    for (const r of rows) {
        if (r.presAlt != null && r.presAlt >= FLOAT_ALT_LO && r.presAlt <= FLOAT_ALT_HI) wasFloating = true;
        if (
            wasFloating &&
            r.presAlt != null &&
            r.presAlt < FLOAT_ALT_LO - 400 &&
            r.t > launchT + 60 * 60_000 &&
            !out.some((e) => e.kind === 'coast')
        ) {
            out.push({ kind: 'coast', label: 'COAST', t: r.t });
            break;
        }
    }

    const lastPacketT = rows[rows.length - 1].t;
    const lastGps = [...rows].reverse().find(hasGps);
    if (lastGps && lastGps.t < lastPacketT - 30 * 60_000 && !out.some((e) => e.kind === 'landfall')) {
        out.push({ kind: 'landfall', label: 'LANDFALL', t: lastGps.t });
    }

    out.push({ kind: 'now', label: 'NOW', t: lastPacketT });

    const byKind = new Map<FlightEventKind, FlightEvent>();
    for (const e of out) {
        const prev = byKind.get(e.kind);
        if (!prev || e.t >= prev.t) byKind.set(e.kind, e);
    }
    return EVENT_ORDER.map((k) => byKind.get(k)).filter((e): e is FlightEvent => e != null);
}

function buildSegmentsBetween(rows: TelemetryRow[], t0: number, t1: number): NarrativeSegment[] {
    const windowRows = rows.filter((r) => r.t >= t0 && r.t <= t1);
    if (windowRows.length < 2) {
        return [{ type: 'signal', t0, t1, widthFrac: 1 }];
    }

    const pieces: NarrativeSegment[] = [];
    let segStart = t0;
    for (let i = 1; i < windowRows.length; i++) {
        const prev = windowRows[i - 1];
        const cur = windowRows[i];
        const dt = cur.t - prev.t;
        if (dt >= GAP_LABEL_MS) {
            if (cur.t > segStart) {
                pieces.push({ type: 'signal', t0: segStart, t1: prev.t, widthFrac: 0 });
            }
            pieces.push({
                type: 'gap',
                t0: prev.t,
                t1: cur.t,
                label: fmtGapLabel(dt),
                widthFrac: GAP_RAIL_FRAC,
            });
            segStart = cur.t;
        }
    }
    if (t1 > segStart) {
        pieces.push({ type: 'signal', t0: segStart, t1, widthFrac: 0 });
    }
    return pieces.length ? pieces : [{ type: 'signal', t0, t1, widthFrac: 1 }];
}

function allocateWidths(segments: NarrativeSegment[]): NarrativeSegment[] {
    const gaps = segments.filter((s): s is NarrativeGapSegment => s.type === 'gap');
    const signals = segments.filter((s): s is NarrativeSignalSegment => s.type === 'signal');
    const gapTotal = gaps.reduce((s, g) => s + g.widthFrac, 0);
    const signalBudget = Math.max(0.2, 1 - gapTotal);
    const signalWeight = signals.map((s) => Math.sqrt(Math.max(60_000, s.t1 - s.t0)));
    const wSum = signalWeight.reduce((a, b) => a + b, 0) || 1;

    return segments.map((seg) => {
        if (seg.type === 'gap') return seg;
        const i = signals.indexOf(seg);
        const frac = Math.max(MIN_SIGNAL_FRAC, (signalWeight[i] / wSum) * signalBudget);
        return { ...seg, widthFrac: frac };
    });
}

export function buildFlightNarrative(
    rows: TelemetryRow[],
    opts?: { launchedAt?: number | null },
): FlightNarrative | null {
    if (rows.length === 0) return null;

    const events = detectFlightEvents(rows, opts);
    const packetEndT = rows[rows.length - 1].t;
    const tStart = events[0]?.t ?? rows[0].t;
    const tEnd = packetEndT;

    const rawSegments: NarrativeSegment[] = [];
    for (let i = 0; i < events.length - 1; i++) {
        rawSegments.push(...buildSegmentsBetween(rows, events[i].t, events[i + 1].t));
    }
    if (rawSegments.length === 0) {
        rawSegments.push(...buildSegmentsBetween(rows, tStart, tEnd));
    }

    const segments = allocateWidths(rawSegments);
    const totalWidth = segments.reduce((s, seg) => s + seg.widthFrac, 0) || 1;

    const cum: Array<{ seg: NarrativeSegment; f0: number; f1: number }> = [];
    let f = 0;
    for (const seg of segments) {
        const w = seg.widthFrac / totalWidth;
        cum.push({ seg, f0: f, f1: f + w });
        f += w;
    }

    function fractionToTime(frac: number): number {
        const f = Math.max(0, Math.min(1, frac));
        const hit = cum.find((c) => f >= c.f0 && f <= c.f1) ?? cum[cum.length - 1];
        if (!hit) return packetEndT;
        const local = hit.f1 > hit.f0 ? (f - hit.f0) / (hit.f1 - hit.f0) : 0;
        if (hit.seg.type === 'gap') {
            return hit.seg.t0 + (hit.seg.t1 - hit.seg.t0) * 0.5;
        }
        return hit.seg.t0 + (hit.seg.t1 - hit.seg.t0) * local;
    }

    function timeToFraction(t: number): number {
        const hit = cum.find((c) => t >= c.seg.t0 && t <= c.seg.t1);
        if (!hit) {
            if (t <= tStart) return 0;
            return 1;
        }
        const local = hit.seg.t1 > hit.seg.t0 ? (t - hit.seg.t0) / (hit.seg.t1 - hit.seg.t0) : 0;
        if (hit.seg.type === 'gap') {
            return hit.f0 + (hit.f1 - hit.f0) * 0.5;
        }
        return hit.f0 + (hit.f1 - hit.f0) * local;
    }

    return {
        events,
        segments,
        tStart,
        tEnd,
        packetEndT,
        timeToFraction,
        fractionToTime,
    };
}

export type PickablePathPoint = { lat: number; lon: number; t: number };

/** Nearest time on a polyline (GPS or hindcast) from a map click. */
export function nearestTimeOnPath(
    path: PickablePathPoint[],
    lng: number,
    lat: number,
    maxDistKm = 120,
): number | null {
    if (path.length === 0) return null;
    if (path.length === 1) {
        const d = haversineKm(path[0].lat, path[0].lon, lat, lng);
        return d <= maxDistKm ? path[0].t : null;
    }

    let bestT = path[0].t;
    let bestD = Infinity;

    for (let i = 1; i < path.length; i++) {
        const a = path[i - 1];
        const b = path[i];
        const { frac, distKm } = projectToSegmentKm(a.lat, a.lon, b.lat, b.lon, lat, lng);
        if (distKm < bestD) {
            bestD = distKm;
            bestT = a.t + frac * (b.t - a.t);
        }
    }
    return bestD <= maxDistKm ? bestT : null;
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) *
            Math.cos((lat2 * Math.PI) / 180) *
            Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

function projectToSegmentKm(
    lat0: number,
    lon0: number,
    lat1: number,
    lon1: number,
    latP: number,
    lonP: number,
): { frac: number; distKm: number } {
    const cosLat = Math.cos((latP * Math.PI) / 180);
    const x0 = lon0 * cosLat * 111.32;
    const y0 = lat0 * 111.32;
    const x1 = lon1 * cosLat * 111.32;
    const y1 = lat1 * 111.32;
    const xp = lonP * cosLat * 111.32;
    const yp = latP * 111.32;
    const dx = x1 - x0;
    const dy = y1 - y0;
    const len2 = dx * dx + dy * dy;
    const frac = len2 < 1e-9 ? 0 : Math.max(0, Math.min(1, ((xp - x0) * dx + (yp - y0) * dy) / len2));
    const xc = x0 + frac * dx;
    const yc = y0 + frac * dy;
    const distKm = Math.hypot(xp - xc, yp - yc);
    return { frac, distKm };
}
