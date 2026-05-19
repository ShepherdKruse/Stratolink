import { fetchHourlyWindAtPoint, meteoWindToUV, windAtTime, type HourlyWind } from './openMeteoForecast';

export type DriftPoint = {
    lat: number;
    lon: number;
    time: string;
    source: 'start' | 'predicted';
    windSpeedMs?: number;
    windDirDeg?: number;
};

const METERS_PER_DEG_LAT = 111_000;

/**
 * Rough constant-altitude drift: balloon moves with the wind at the selected pressure level.
 * Re-fetches Open-Meteo hourly wind at the current position every `refetchEverySteps`.
 */
export async function computeDriftForecast(opts: {
    startLat: number;
    startLon: number;
    pressureHpa: number;
    durationHours?: number;
    stepMinutes?: number;
    refetchEverySteps?: number;
    startTime?: Date;
}): Promise<DriftPoint[]> {
    const durationHours = opts.durationHours ?? 24;
    const stepMinutes = opts.stepMinutes ?? 30;
    const refetchEverySteps = opts.refetchEverySteps ?? 4;
    const startTime = opts.startTime ?? new Date();

    const steps = Math.floor((durationHours * 60) / stepMinutes);
    const points: DriftPoint[] = [
        {
            lat: opts.startLat,
            lon: opts.startLon,
            time: startTime.toISOString(),
            source: 'start',
        },
    ];

    let lat = opts.startLat;
    let lon = opts.startLon;
    let series: HourlyWind[] | null = null;

    for (let i = 1; i <= steps; i++) {
        const when = new Date(startTime.getTime() + i * stepMinutes * 60_000);

        if (series === null || i % refetchEverySteps === 0) {
            series = await fetchHourlyWindAtPoint(lat, lon, opts.pressureHpa);
        }

        const w = windAtTime(series, when);
        if (!w) break;

        const { u, v } = meteoWindToUV(w.speedMs, w.directionDeg);
        const dt = stepMinutes * 60;
        const cosLat = Math.cos((lat * Math.PI) / 180);
        const dLat = (v * dt) / METERS_PER_DEG_LAT;
        const dLon = (u * dt) / (METERS_PER_DEG_LAT * Math.max(0.2, cosLat));

        lat += dLat;
        lon += dLon;

        if (lat < -85 || lat > 85 || lon < -180 || lon > 180) break;

        points.push({
            lat,
            lon,
            time: when.toISOString(),
            source: 'predicted',
            windSpeedMs: w.speedMs,
            windDirDeg: w.directionDeg,
        });
    }

    return points;
}
