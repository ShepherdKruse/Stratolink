import { integrateBalloonPath, type BiasLike } from './balloonIntegrate';
import { boundsForForecast, fetchWindGrid, snapPressureHpa } from './fetchWindGrid';
import type { ForecastGpsFix } from './forecastTypes';
import { windFieldToGfsGrid } from './gfsGrid';

/** If last GPS fix is older than this, dead-reckon to "now" before forecasting forward. */
export const STALE_GPS_THRESHOLD_H = 1;

const MAX_GAP_H = 72;

export function gpsGapHours(lastFix: ForecastGpsFix, now = new Date()): number {
    const ms = now.getTime() - new Date(lastFix.time_utc).getTime();
    return ms > 0 ? ms / 3_600_000 : 0;
}

export type ResolvedForecastStart = {
    lat: number;
    lon: number;
    time_utc: string;
    alt_m?: number;
    /** Hourly [lon, lat] from last GPS fix to implied now (empty if GPS fresh). */
    implied_drift_lonlat: Array<[number, number]>;
    stale_gps?: {
        gap_hours: number;
        last_fix_time_utc: string;
        wind_field_time_utc: string;
    };
};

/**
 * When GPS is stale, integrate GFS at the last-fix time through the gap to an implied
 * current position, then run the forward forecast from there.
 */
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

    const levelHpa = snapPressureHpa(opts.pressureHpa);
    const lastFixTime = new Date(opts.lastFix.time_utc);
    const marginPts = [
        { lat: opts.lastFix.lat, lon: opts.lastFix.lon },
        ...opts.observedTrackLonLat.map(([lon, lat]) => ({ lat, lon })),
    ];
    const gapBounds = boundsForForecast(marginPts, opts.gpsFixes, gapH);
    const spanDeg = Math.max(gapBounds.latMax - gapBounds.latMin, gapBounds.lonMax - gapBounds.lonMin);
    const gridStep = spanDeg > 22 ? 3.5 : 2.5;

    const gapField = await fetchWindGrid(gapBounds, levelHpa, gridStep, lastFixTime);
    const gapGfs = windFieldToGfsGrid(gapField, gridStep);
    const neutral = { speedM: 1, dirOffDeg: 0, altPertHPa: 0 };
    const gapPath = integrateBalloonPath(
        opts.lastFix.lat,
        opts.lastFix.lon,
        gapGfs,
        opts.bias,
        neutral,
        gapH,
    );
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
            wind_field_time_utc: lastFixTime.toISOString(),
        },
    };
}
