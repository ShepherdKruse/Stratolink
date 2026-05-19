/**
 * GFS winds via Open-Meteo (free, no key). Same model family as earth.nullschool.net.
 * @see https://open-meteo.com/en/docs/gfs-api
 */

import { pressureHpaToNullschoolLevel } from './nullschool';

export type HourlyWind = {
    time: string;
    speedMs: number;
    directionDeg: number;
};

/** Meteorological wind direction (from) → u east, v north in m/s. */
export function meteoWindToUV(speedMs: number, directionDeg: number): { u: number; v: number } {
    const rad = (directionDeg * Math.PI) / 180;
    return {
        u: -speedMs * Math.sin(rad),
        v: -speedMs * Math.cos(rad),
    };
}

function openMeteoLevelKey(hPa: number): string {
    const id = pressureHpaToNullschoolLevel(hPa).replace('hPa', '');
    return id;
}

export async function fetchHourlyWindAtPoint(
    lat: number,
    lon: number,
    pressureHpa: number,
    forecastDays = 3,
): Promise<HourlyWind[]> {
    const level = openMeteoLevelKey(pressureHpa);
    const speedKey = `wind_speed_${level}hPa`;
    const dirKey = `wind_direction_${level}hPa`;

    const url = new URL('https://api.open-meteo.com/v1/forecast');
    url.searchParams.set('latitude', String(lat));
    url.searchParams.set('longitude', String(lon));
    url.searchParams.set('hourly', `${speedKey},${dirKey}`);
    url.searchParams.set('forecast_days', String(forecastDays));
    url.searchParams.set('wind_speed_unit', 'ms');
    url.searchParams.set('timezone', 'UTC');

    const res = await fetch(url.toString(), { next: { revalidate: 1800 } });
    if (!res.ok) {
        throw new Error(`Open-Meteo error ${res.status}`);
    }

    const data = (await res.json()) as {
        hourly: Record<string, (number | null)[] | string[]>;
    };
    const times = data.hourly.time as string[];
    const speeds = data.hourly[speedKey] as (number | null)[];
    const dirs = data.hourly[dirKey] as (number | null)[];

    return times
        .map((time, i) => ({
            time,
            speedMs: speeds[i] ?? 0,
            directionDeg: dirs[i] ?? 0,
        }))
        .filter((r) => Number.isFinite(r.speedMs) && Number.isFinite(r.directionDeg));
}

/** Pick the hourly sample closest to a target instant. */
export function windAtTime(series: HourlyWind[], when: Date): HourlyWind | null {
    if (!series.length) return null;
    const t = when.getTime();
    let best = series[0];
    let bestDiff = Math.abs(new Date(best.time).getTime() - t);
    for (const row of series) {
        const diff = Math.abs(new Date(row.time).getTime() - t);
        if (diff < bestDiff) {
            bestDiff = diff;
            best = row;
        }
    }
    return best;
}
