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
    tilt: (number | null)[];
    sway: (number | null)[];
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

    const tilt = rows.map((r) => {
        if (r.ax == null || r.ay == null) return null;
        return Math.sqrt(r.ax * r.ax + r.ay * r.ay);
    });
    const sway = rows.map((r) => (r.az != null ? Math.abs(r.az) : null));

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
        tilt,
        sway,
        gw,
        hdop,
    };
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

/** Ascent rate m/s from last two pressure-altitude samples. */
export function ascentRateMps(series: FlightSeries): number | null {
    const pts = series.altPres;
    const times = series.times;
    if (pts.length < 2) return null;
    const i = pts.length - 1;
    const j = i - 1;
    const a = pts[j];
    const b = pts[i];
    if (a == null || b == null) return null;
    const dt = (times[i] - times[j]) / 1000;
    if (dt <= 0) return null;
    return (b - a) / dt;
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
