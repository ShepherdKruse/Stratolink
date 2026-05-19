import type { WindVector } from './types';

export type DriftPoint = {
    lat: number;
    lon: number;
    time: string;
    source: 'start' | 'predicted';
    windSpeedMs?: number;
    windDirDeg?: number;
};

export type WindModifier = (wind: WindVector) => WindVector;

const METERS_PER_DEG_LAT = 111_000;

export function uvToSpeedDir(u: number, v: number): { speedMs: number; directionDeg: number } {
    const speedMs = Math.sqrt(u * u + v * v);
    const directionDeg = ((Math.atan2(-u, -v) * 180) / Math.PI + 360) % 360;
    return { speedMs, directionDeg };
}

export function scaleWind(wind: WindVector, factor: number): WindVector {
    return { u: wind.u * factor, v: wind.v * factor };
}

export function rotateWind(wind: WindVector, degrees: number): WindVector {
    const rad = (degrees * Math.PI) / 180;
    const cos = Math.cos(rad);
    const sin = Math.sin(rad);
    return {
        u: wind.u * cos - wind.v * sin,
        v: wind.u * sin + wind.v * cos,
    };
}

export function integrateDriftPath(opts: {
    startLat: number;
    startLon: number;
    startTime: Date;
    durationHours: number;
    stepMinutes: number;
    sampleWind: (lat: number, lon: number, when: Date) => WindVector | null;
    modifyWind?: WindModifier;
}): DriftPoint[] {
    const { startLat, startLon, startTime, durationHours, stepMinutes, sampleWind, modifyWind } = opts;
    const steps = Math.floor((durationHours * 60) / stepMinutes);
    const points: DriftPoint[] = [
        {
            lat: startLat,
            lon: startLon,
            time: startTime.toISOString(),
            source: 'start',
        },
    ];

    let lat = startLat;
    let lon = startLon;

    for (let i = 1; i <= steps; i++) {
        const when = new Date(startTime.getTime() + i * stepMinutes * 60_000);
        let wind = sampleWind(lat, lon, when);
        if (!wind) break;
        if (modifyWind) wind = modifyWind(wind);

        const { speedMs, directionDeg } = uvToSpeedDir(wind.u, wind.v);
        const dt = stepMinutes * 60;
        const cosLat = Math.cos((lat * Math.PI) / 180);
        const dLat = (wind.v * dt) / METERS_PER_DEG_LAT;
        const dLon = (wind.u * dt) / (METERS_PER_DEG_LAT * Math.max(0.2, cosLat));

        lat += dLat;
        lon += dLon;

        if (lat < -85 || lat > 85) break;

        points.push({
            lat,
            lon,
            time: when.toISOString(),
            source: 'predicted',
            windSpeedMs: speedMs,
            windDirDeg: Math.round(directionDeg),
        });
    }

    return points;
}
