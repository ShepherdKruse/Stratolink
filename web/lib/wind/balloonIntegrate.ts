import { windAt, type GfsGrid } from './gfsGrid';

export const BALLOON_STEP_HOURS = 1 / 6;
const ALT_TO_WIND_FACTOR = 0.015;

export type BiasLike = { speedMult: number; dirOffsetDeg: number };
export type Perturbation = { speedM: number; dirOffDeg: number; altPertHPa: number };

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

/** Bias-corrected drift integration on a GFS grid; one [lon, lat] point per hour. */
export function integrateBalloonPath(
    startLat: number,
    startLon: number,
    gfs: GfsGrid,
    bias: BiasLike,
    pert: Perturbation,
    totalHours: number,
): Array<[number, number]> {
    const { speedMult, dirOffsetDeg } = bias;
    const { speedM, dirOffDeg, altPertHPa } = pert;

    const totalSteps = Math.round(totalHours / BALLOON_STEP_HOURS);
    const stepSec = BALLOON_STEP_HOURS * 3600;
    const dirRad = ((dirOffsetDeg + dirOffDeg) * Math.PI) / 180;
    const cosD = Math.cos(dirRad);
    const sinD = Math.sin(dirRad);
    const altScale = 1 + altPertHPa * ALT_TO_WIND_FACTOR;

    let lat = startLat;
    let lon = startLon;
    const path: Array<[number, number]> = [[round4(lon), round4(lat)]];
    const stepsPerHour = Math.round(1 / BALLOON_STEP_HOURS);

    for (let s = 1; s <= totalSteps; s++) {
        const { u, v } = windAt(gfs, lat, lon);
        const k = speedMult * speedM * altScale;
        const uK = u * k;
        const vK = v * k;
        const uR = uK * cosD - vK * sinD;
        const vR = uK * sinD + vK * cosD;

        const cosLat = Math.max(Math.cos((lat * Math.PI) / 180), 0.05);
        lat += (vR * stepSec) / 111_320;
        lon += (uR * stepSec) / (111_320 * cosLat);

        if (s % stepsPerHour === 0) {
            path.push([round4(lon), round4(lat)]);
        }
    }

    return path;
}
