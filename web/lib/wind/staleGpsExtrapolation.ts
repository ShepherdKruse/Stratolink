import { BALLOON_STEP_HOURS } from './balloonIntegrate';
import type { BiasLike } from './balloonIntegrate';
import { snapPressureHpa } from './fetchWindGrid';
import type { ForecastGpsFix } from './forecastTypes';
import {
    fetchHourlyWindAtPoint,
    meteoWindToUV,
    windAtOrBefore,
    type HourlyWind,
} from './openMeteoForecast';

/** How often to re-fetch full stale-gap + forecast from the server while GPS is stale. */
export const STALE_GAP_REFRESH_MS = 15 * 60_000;

/** If last GPS fix is older than this, dead-reckon to "now" before forecasting forward. */
export const STALE_GPS_THRESHOLD_H = 1;

export const GAP_WIND_MODE = 'hourly_series' as const;

const MAX_GAP_H = 72;
const REFETCH_EVERY_H = 3;

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

export function gpsGapHours(lastFix: ForecastGpsFix, now = new Date()): number {
    const ms = now.getTime() - new Date(lastFix.time_utc).getTime();
    return ms > 0 ? ms / 3_600_000 : 0;
}

export function gpsGapHoursFromMs(lastFixMs: number, nowMs = Date.now()): number {
    return lastFixMs > 0 ? Math.max(0, (nowMs - lastFixMs) / 3_600_000) : 0;
}

export function formatGapAge(gapH: number): string {
    if (gapH < 1 / 60) return '<1m';
    if (gapH < 1) return `${Math.round(gapH * 60)}m`;
    const h = Math.floor(gapH);
    const m = Math.round((gapH - h) * 60);
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/**
 * Lightweight client extension between server recomputes — holds last drift point
 * and steps forward with endpoint wind so the dashed line grows with clock time.
 */
export function extrapolateDriftTail(
    path: Array<[number, number]>,
    computedGapH: number,
    liveGapH: number,
    wind?: { speed_mps: number; dir_deg: number },
): Array<[number, number]> {
    const extraH = liveGapH - computedGapH;
    if (extraH <= 1 / 120 || path.length < 1 || !wind || wind.speed_mps <= 0) return path;

    let lat = path[path.length - 1][1];
    let lon = path[path.length - 1][0];
    const out = [...path];
    const stepMinutes = BALLOON_STEP_HOURS * 60;
    const steps = Math.round((extraH * 60) / stepMinutes);
    const stepsPerHour = Math.round(1 / BALLOON_STEP_HOURS);
    let { u, v } = meteoWindToUV(wind.speed_mps, wind.dir_deg);

    for (let s = 1; s <= steps; s++) {
        const stepSec = stepMinutes * 60;
        const cosLat = Math.max(Math.cos((lat * Math.PI) / 180), 0.05);
        lat += (v * stepSec) / 111_320;
        lon += (u * stepSec) / (111_320 * cosLat);
        if (s % stepsPerHour === 0) {
            out.push([round4(lon), round4(lat)]);
        }
    }
    return out;
}

function applyBiasToWind(u: number, v: number, bias: BiasLike): { u: number; v: number } {
    const dirRad = (bias.dirOffsetDeg * Math.PI) / 180;
    const k = bias.speedMult;
    const uK = u * k;
    const vK = v * k;
    return {
        u: uK * Math.cos(dirRad) - vK * Math.sin(dirRad),
        v: uK * Math.sin(dirRad) + vK * Math.cos(dirRad),
    };
}

/**
 * Integrate stale-GPS gap using hourly GFS at each step (with past_days), not a single
 * snapshot — avoids Open-Meteo falling back to "now" when the fix is hours old.
 */
/** Hourly GFS integration forward from a fix (used for stale gap and hindcast replay). */
export async function integrateHourlyDriftForward(
    lastFix: ForecastGpsFix,
    pressureHpa: number,
    gapH: number,
    bias: BiasLike,
): Promise<Array<[number, number]>> {
    const levelHpa = snapPressureHpa(pressureHpa);
    const startTime = new Date(lastFix.time_utc);
    const stepMinutes = BALLOON_STEP_HOURS * 60;
    const steps = Math.round((gapH * 60) / stepMinutes);
    const stepsPerHour = Math.round(1 / BALLOON_STEP_HOURS);
    const anchorMs = startTime.getTime();
    const hoursAgo = (Date.now() - anchorMs) / 3_600_000;
    const pastDays = Math.min(92, Math.ceil((Math.max(0, hoursAgo) + gapH) / 24) + 2);

    let lat = lastFix.lat;
    let lon = lastFix.lon;
    const path: Array<[number, number]> = [[round4(lon), round4(lat)]];
    let series: HourlyWind[] = await fetchHourlyWindAtPoint(lastFix.lat, lastFix.lon, levelHpa, {
        pastDays,
        forecastDays: 2,
    });
    let hoursSinceRefetch = 0;

    for (let s = 1; s <= steps; s++) {
        const when = new Date(startTime.getTime() + s * stepMinutes * 60_000);

        if (hoursSinceRefetch >= REFETCH_EVERY_H) {
            series = await fetchHourlyWindAtPoint(lat, lon, levelHpa, { pastDays, forecastDays: 2 });
            hoursSinceRefetch = 0;
        }
        hoursSinceRefetch += BALLOON_STEP_HOURS;

        const sample = windAtOrBefore(series, when);
        if (!sample) break;

        let { u, v } = meteoWindToUV(sample.speedMs, sample.directionDeg);
        ({ u, v } = applyBiasToWind(u, v, bias));

        const stepSec = stepMinutes * 60;
        const cosLat = Math.max(Math.cos((lat * Math.PI) / 180), 0.05);
        lat += (v * stepSec) / 111_320;
        lon += (u * stepSec) / (111_320 * cosLat);

        if (s % stepsPerHour === 0) {
            path.push([round4(lon), round4(lat)]);
        }
    }

    return path;
}

export type ResolvedForecastStart = {
    lat: number;
    lon: number;
    time_utc: string;
    alt_m?: number;
    implied_drift_lonlat: Array<[number, number]>;
    stale_gps?: {
        gap_hours: number;
        last_fix_time_utc: string;
        wind_field_time_utc: string;
        wind_mode: typeof GAP_WIND_MODE;
    };
};

export async function resolveForecastStart(opts: {
    lastFix: ForecastGpsFix;
    gpsFixes: ForecastGpsFix[];
    observedTrackLonLat: Array<[number, number]>;
    pressureHpa: number;
    bias: BiasLike;
    existingDriftLonLat?: Array<[number, number]>;
    now?: Date;
}): Promise<ResolvedForecastStart> {
    const now = opts.now ?? new Date();
    const gapH = Math.min(gpsGapHours(opts.lastFix, now), MAX_GAP_H);

    if (gapH < STALE_GPS_THRESHOLD_H) {
        return {
            lat: opts.lastFix.lat,
            lon: opts.lastFix.lon,
            time_utc: opts.lastFix.time_utc,
            alt_m: opts.lastFix.alt_m,
            implied_drift_lonlat: opts.existingDriftLonLat ?? [],
        };
    }

    const gapPath = await integrateHourlyDriftForward(opts.lastFix, opts.pressureHpa, gapH, opts.bias);
    const end = gapPath[gapPath.length - 1] ?? [opts.lastFix.lon, opts.lastFix.lat];

    return {
        lat: end[1],
        lon: end[0],
        time_utc: now.toISOString(),
        alt_m: opts.lastFix.alt_m,
        implied_drift_lonlat: gapPath,
        stale_gps: {
            gap_hours: Math.round(gapH * 10) / 10,
            last_fix_time_utc: opts.lastFix.time_utc,
            wind_field_time_utc: opts.lastFix.time_utc,
            wind_mode: GAP_WIND_MODE,
        },
    };
}
