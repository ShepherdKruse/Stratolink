import type { ForecastGpsFix } from './forecastTypes';

/** If the last GPS fix is older than this, dead-reckon to "now" before forecasting forward. */
export const STALE_GPS_THRESHOLD_H = 1;

/* The stale-GPS dead-reckon (last fix → now) is integrated through the shared
 * NOAA WindCube alongside the forward forecast (see monteCarloForecast). This
 * label reports that in the forecast metadata. The per-point Open-Meteo
 * integrators that used to live here were deleted in Oct 2026. */
export const GAP_WIND_MODE = 'gfs_cube' as const;

export function gpsGapHours(lastFix: ForecastGpsFix, now = new Date()): number {
    const ms = now.getTime() - new Date(lastFix.time_utc).getTime();
    return ms > 0 ? ms / 3_600_000 : 0;
}
