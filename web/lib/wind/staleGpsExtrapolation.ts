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
async function integrateGapHourly(
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
    const pastDays = Math.min(92, Math.ceil(gapH / 24) + 1);

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

    const gapPath = await integrateGapHourly(opts.lastFix, opts.pressureHpa, gapH, opts.bias);
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
