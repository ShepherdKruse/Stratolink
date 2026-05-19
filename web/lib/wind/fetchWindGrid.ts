import { meteoWindToUV, windAtTime, type HourlyWind } from './openMeteoForecast';
import type { GridPoint, WindField } from './types';

export type WindGridBounds = {
    latMin: number;
    latMax: number;
    lonMin: number;
    lonMax: number;
};

const GFS_PRESSURE_LEVELS_HPA = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30];

/** Snap telemetry pressure to nearest Open-Meteo GFS level. */
export function snapPressureHpa(hpa: number): number {
    if (!Number.isFinite(hpa) || hpa <= 0) return 250;
    let best = GFS_PRESSURE_LEVELS_HPA[0];
    let bestDiff = Math.abs(hpa - best);
    for (const level of GFS_PRESSURE_LEVELS_HPA) {
        const d = Math.abs(hpa - level);
        if (d < bestDiff) {
            best = level;
            bestDiff = d;
        }
    }
    return best;
}

/** Fetch a lat/lon grid of current-hour winds via Open-Meteo (batched multi-location). */
export async function fetchWindGrid(
    bounds: WindGridBounds,
    pressureHpa: number,
    gridStepDeg = 1.25,
    at: Date = new Date(),
): Promise<WindField> {
    const levelHpa = snapPressureHpa(pressureHpa);
    const lats: number[] = [];
    const lons: number[] = [];
    for (let lat = bounds.latMin; lat <= bounds.latMax + 0.001; lat += gridStepDeg) {
        for (let lon = bounds.lonMin; lon <= bounds.lonMax + 0.001; lon += gridStepDeg) {
            lats.push(Math.round(lat * 100) / 100);
            lons.push(Math.round(lon * 100) / 100);
        }
    }

    const grid: GridPoint[] = [];

    // Open-Meteo accepts comma-separated lists (max ~100 locations per call); chunk if needed
    const chunkSize = 80;
    for (let i = 0; i < lats.length; i += chunkSize) {
        const latChunk = lats.slice(i, i + chunkSize);
        const lonChunk = lons.slice(i, i + chunkSize);
        const level = String(levelHpa);
        const speedKey = `wind_speed_${level}hPa`;
        const dirKey = `wind_direction_${level}hPa`;

        const url = new URL('https://api.open-meteo.com/v1/forecast');
        url.searchParams.set('latitude', latChunk.join(','));
        url.searchParams.set('longitude', lonChunk.join(','));
        url.searchParams.set('hourly', `${speedKey},${dirKey}`);
        url.searchParams.set('wind_speed_unit', 'ms');
        url.searchParams.set('timezone', 'UTC');
        url.searchParams.set('forecast_days', '2');

        const res = await fetch(url.toString(), { next: { revalidate: 900 } });
        if (!res.ok) throw new Error(`Open-Meteo grid error ${res.status}`);

        const payloads = (await res.json()) as Array<{
            latitude: number;
            longitude: number;
            hourly: Record<string, (number | null)[] | string[]>;
        }>;

        const list = Array.isArray(payloads) ? payloads : [payloads as unknown as (typeof payloads)[0]];

        for (const p of list) {
            const series: HourlyWind[] = (p.hourly.time as string[]).map((time, idx) => ({
                time,
                speedMs: (p.hourly[speedKey] as number[])[idx] ?? 0,
                directionDeg: (p.hourly[dirKey] as number[])[idx] ?? 0,
            }));
            const w = windAtTime(series, at);
            if (!w) continue;
            const { u, v } = meteoWindToUV(w.speedMs, w.directionDeg);
            grid.push({ lat: p.latitude, lon: p.longitude, wind: { u, v } });
        }
    }

    return {
        timestamp: at.toISOString(),
        altitudeBand: levelHpa < 400 ? '15km' : '5km',
        grid,
        gridResolution: gridStepDeg,
        bounds: { ...bounds },
    };
}

/** Expand bounds to include track + margin. */
export function boundsFromPoints(
    points: Array<{ lat: number; lon: number }>,
    marginDeg = 3,
): WindGridBounds {
    const lats = points.map((p) => p.lat);
    const lons = points.map((p) => p.lon);
    return {
        latMin: Math.min(...lats) - marginDeg,
        latMax: Math.max(...lats) + marginDeg,
        lonMin: Math.min(...lons) - marginDeg,
        lonMax: Math.max(...lons) + marginDeg,
    };
}
