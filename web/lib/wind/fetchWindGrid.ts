import { meteoWindToUV, windAtTime, type HourlyWind } from './openMeteoForecast';
import { openMeteoFetch } from './openMeteoFetch';
import { windFieldToGfsGrid, type GfsGrid } from './gfsGrid';
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
        const ageH = (Date.now() - at.getTime()) / 3_600_000;
        if (ageH > 6) {
            url.searchParams.set('past_days', String(Math.min(92, Math.ceil(ageH / 24) + 3)));
        }

        const res = await openMeteoFetch(url.toString());
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

type GridPointHourly = { lat: number; lon: number; series: HourlyWind[] };

/** Fetch hourly wind series at each grid point (one Open-Meteo batch per chunk). */
async function fetchGridHourlySeries(
    bounds: WindGridBounds,
    levelHpa: number,
    gridStepDeg: number,
    windowStart: Date,
    hourCount: number,
): Promise<GridPointHourly[]> {
    const lats: number[] = [];
    const lons: number[] = [];
    for (let lat = bounds.latMin; lat <= bounds.latMax + 0.001; lat += gridStepDeg) {
        for (let lon = bounds.lonMin; lon <= bounds.lonMax + 0.001; lon += gridStepDeg) {
            lats.push(Math.round(lat * 100) / 100);
            lons.push(Math.round(lon * 100) / 100);
        }
    }

    const points: GridPointHourly[] = [];
    const chunkSize = 80;
    const forecastDays = Math.min(16, Math.ceil(hourCount / 24) + 2);
    const ageH = (Date.now() - windowStart.getTime()) / 3_600_000;
    const pastDays =
        ageH > 6 ? Math.min(92, Math.ceil(ageH / 24) + Math.ceil(hourCount / 24) + 3) : 0;

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
        url.searchParams.set('forecast_days', String(forecastDays));
        if (pastDays > 0) url.searchParams.set('past_days', String(pastDays));

        const res = await openMeteoFetch(url.toString());
        if (!res.ok) throw new Error(`Open-Meteo grid error ${res.status}`);

        const payloads = (await res.json()) as Array<{
            latitude: number;
            longitude: number;
            hourly: Record<string, (number | null)[] | string[]>;
        }>;
        const list = Array.isArray(payloads) ? payloads : [payloads];

        for (const p of list) {
            const series: HourlyWind[] = (p.hourly.time as string[]).map((time, idx) => ({
                time,
                speedMs: (p.hourly[speedKey] as number[])[idx] ?? 0,
                directionDeg: (p.hourly[dirKey] as number[])[idx] ?? 0,
            }));
            points.push({ lat: p.latitude, lon: p.longitude, series });
        }
    }

    return points;
}

function gfsGridFromHourlyPoints(
    points: GridPointHourly[],
    bounds: WindGridBounds,
    gridStepDeg: number,
    when: Date,
): GfsGrid {
    const dLat = gridStepDeg;
    const dLon = gridStepDeg;
    const lat0 = bounds.latMin;
    const lon0 = bounds.lonMin;
    const nLat = Math.max(2, Math.round((bounds.latMax - lat0) / dLat) + 1);
    const nLon = Math.max(2, Math.round((bounds.lonMax - lon0) / dLon) + 1);
    const U = new Float32Array(nLat * nLon);
    const V = new Float32Array(nLat * nLon);

    for (const p of points) {
        const w = windAtTime(p.series, when);
        if (!w) continue;
        const gi = Math.round((p.lat - lat0) / dLat);
        const gj = Math.round((p.lon - lon0) / dLon);
        if (gi < 0 || gi >= nLat || gj < 0 || gj >= nLon) continue;
        const { u, v } = meteoWindToUV(w.speedMs, w.directionDeg);
        U[gi * nLon + gj] = u;
        V[gi * nLon + gj] = v;
    }

    return { lat0, dLat, nLat, lon0, dLon, nLon, U, V };
}

/**
 * Hourly GFS grids for long-gap reconstruction — one grid per hour from gap start.
 * Uses the same spatial grid as fetchWindGrid; winds vary by hour via Open-Meteo hourly series.
 */
export async function fetchWindGridHourlySeries(
    bounds: WindGridBounds,
    pressureHpa: number,
    gridStepDeg: number,
    gapStart: Date,
    gapHours: number,
): Promise<GfsGrid[]> {
    const levelHpa = snapPressureHpa(pressureHpa);
    const nHours = Math.min(96, Math.max(1, Math.ceil(gapHours) + 1));
    const points = await fetchGridHourlySeries(bounds, levelHpa, gridStepDeg, gapStart, nHours);
    if (!points.length) {
        const field = await fetchWindGrid(bounds, levelHpa, gridStepDeg, gapStart);
        const gfs = windFieldToGfsGrid(field, gridStepDeg);
        return Array.from({ length: nHours }, () => gfs);
    }

    const grids: GfsGrid[] = [];
    for (let h = 0; h < nHours; h++) {
        const when = new Date(gapStart.getTime() + h * 3_600_000);
        grids.push(gfsGridFromHourlyPoints(points, bounds, gridStepDeg, when));
    }
    return grids;
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

/**
 * Wind grid large enough for forward integration — pads downwind from recent GPS motion.
 * A track-only bbox (~4°) is too small; the balloon exits the grid after ~12h and stops moving.
 */
export function boundsForForecast(
    points: Array<{ lat: number; lon: number }>,
    gpsFixes: Array<{ lat: number; lon: number; time_utc: string }>,
    forecastHours: number,
): WindGridBounds {
    const base = boundsFromPoints(points, 4);

    let dLatPerH = 0.35;
    let dLonPerH = 0.45;
    if (gpsFixes.length >= 2) {
        const b = gpsFixes[gpsFixes.length - 1];
        const a = gpsFixes[gpsFixes.length - 2];
        const dtH =
            (new Date(b.time_utc).getTime() - new Date(a.time_utc).getTime()) / 3_600_000;
        if (dtH > 0.15) {
            dLatPerH = (b.lat - a.lat) / dtH;
            dLonPerH = (b.lon - a.lon) / dtH;
        }
    }

    const padH = forecastHours * 1.35;
    const padLat = Math.abs(dLatPerH * padH) + 6;
    const padLon = Math.abs(dLonPerH * padH) + 6;
    const up = dLatPerH >= 0 ? padLat : 6;
    const down = dLatPerH <= 0 ? padLat : 6;
    const east = dLonPerH >= 0 ? padLon : 6;
    const west = dLonPerH <= 0 ? padLon : 6;

    return {
        latMin: base.latMin - down,
        latMax: base.latMax + up,
        lonMin: base.lonMin - west,
        lonMax: base.lonMax + east,
    };
}
