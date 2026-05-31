import type { TelemetryRow } from '@/components/dashboard-v2/atoms';

/** Parallel time series consumed by the v3 telemetry panel (design contract). */
export type FlightSeries = {
    times: number[];
    altGps: (number | null)[];
    altPres: (number | null)[];
    batt: (number | null)[];
    solar: (number | null)[];
    temp: (number | null)[];
    press: (number | null)[];
    rssi: (number | null)[];
    snr: (number | null)[];
    sats: (number | null)[];
    sun: number[];
    lux: (number | null)[];
    heading: (number | null)[];
    speed: (number | null)[];
    gw: (number | null)[];
    hdop: (number | null)[];
};

export function buildFlightSeries(rows: TelemetryRow[]): FlightSeries {
    const times = rows.map((r) => r.t);
    const altGps = rows.map((r) => r.alt);
    const altPres = rows.map((r) => r.presAlt);
    const batt = rows.map((r) => r.batt);
    const solar = rows.map((r) => r.sol);
    const temp = rows.map((r) => r.temp);
    const press = rows.map((r) => r.pres);
    const rssi = rows.map((r) => r.rssi);
    const snr = rows.map((r) => r.snr);
    const sats = rows.map((r) => r.sats);
    const lux = rows.map((r) => r.lux);
    const heading = rows.map((r) => r.hdg);
    const speed = rows.map((r) => (r.spd != null ? r.spd * 3.6 : null));
    const hdop = rows.map((r) => r.hdop);
    const gw = rows.map((r) => (r.gateways?.length ? r.gateways.length : 0));

    const sun = solar.map((v) => {
        if (v == null) return 0;
        return Math.min(1, Math.max(0, v / 6.2));
    });

    return {
        times,
        altGps,
        altPres,
        batt,
        solar,
        temp,
        press,
        rssi,
        snr,
        sats,
        sun,
        lux,
        heading,
        speed,
        gw,
        hdop,
    };
}

/** Attitude derived from MEMS accel at one telemetry instant (scrubber-aligned). */
export type PayloadAttitude = {
    /** Degrees from vertical (0 = upright). Meaningful when `reliable`. */
    tiltDeg: number;
    horizontalMs2: number;
    totalMs2: number;
    /** True when |a| ≈ 1g — quasi-static, so tilt from gravity is meaningful. */
    reliable: boolean;
};

/** Tilt from gravity vector; null when accel axes are missing. */
export function computePayloadAttitude(
    ax: number | null,
    ay: number | null,
    az: number | null,
): PayloadAttitude | null {
    if (ax == null || ay == null || az == null) return null;
    const horizontal = Math.hypot(ax, ay);
    const total = Math.hypot(horizontal, az);
    const tiltDeg = (Math.atan2(horizontal, Math.abs(az)) * 180) / Math.PI;
    const reliable = total >= 7 && total <= 12.5;
    return { tiltDeg, horizontalMs2: horizontal, totalMs2: total, reliable };
}

export function last<T>(arr: T[]): T | undefined {
    return arr.length ? arr[arr.length - 1] : undefined;
}

export function lastIndex<T>(arr: T[], pred: (v: T) => boolean): number {
    for (let i = arr.length - 1; i >= 0; i--) {
        if (pred(arr[i] as T)) return i;
    }
    return -1;
}

/** Delta over ~30 min of pressure altitude (m), or null if insufficient data. */
export function altDelta30m(series: FlightSeries): number | null {
    const pts = series.altPres;
    const times = series.times;
    if (pts.length < 2) return null;
    const end = pts.length - 1;
    const tEnd = times[end];
    let start = end;
    for (let i = end - 1; i >= 0; i--) {
        if (tEnd - times[i] >= 30 * 60 * 1000) {
            start = i;
            break;
        }
        start = i;
    }
    const a = pts[start];
    const b = pts[end];
    if (a == null || b == null) return null;
    return Math.round(b - a);
}

/** Index of the last row with `t <= atMs`. */
export function rowIndexAtOrBefore(rows: TelemetryRow[], atMs: number): number {
    let idx = -1;
    for (let i = 0; i < rows.length; i++) {
        if (rows[i].t <= atMs) idx = i;
        else break;
    }
    return idx;
}

/**
 * Vertical speed (m/s) from pressure altitude: Δalt / Δt between the scrubbed
 * packet and the nearest earlier packet that also has presAlt.
 */
export function ascentRateMpsAtScrub(rows: TelemetryRow[], scrubRow: TelemetryRow | null): number | null {
    if (!scrubRow || rows.length < 2) return null;

    const endIdx = rowIndexAtOrBefore(rows, scrubRow.t);
    if (endIdx <= 0) return null;

    const endAlt = rows[endIdx].presAlt;
    const endT = rows[endIdx].t;
    if (endAlt == null || !Number.isFinite(endAlt)) return null;

    for (let j = endIdx - 1; j >= 0; j--) {
        const prevAlt = rows[j].presAlt;
        if (prevAlt == null || !Number.isFinite(prevAlt)) continue;
        const dtSec = (endT - rows[j].t) / 1000;
        if (dtSec <= 0) continue;
        return (endAlt - prevAlt) / dtSec;
    }
    return null;
}

/** Duration since last GPS lock (ms), or null if always locked in window. */
export function noFixDurationMs(series: FlightSeries): number | null {
    const idx = lastIndex(series.sats, (s) => s != null && s > 0);
    if (idx < 0) return null;
    if (idx === series.sats.length - 1) return null;
    const lastFixT = series.times[idx];
    return series.times[series.times.length - 1] - lastFixT;
}

export function maxGatewaysSeen(series: FlightSeries): number {
    let m = 0;
    for (const g of series.gw) {
        if (g != null && g > m) m = g;
    }
    return Math.max(m, 1);
}
