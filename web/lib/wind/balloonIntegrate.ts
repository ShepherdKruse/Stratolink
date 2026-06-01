import { windAt, type GfsGrid } from './gfsGrid';
import { sampleWind, type WindCube } from './windCube';

export const BALLOON_STEP_HOURS = 1 / 6;
const ALT_TO_WIND_FACTOR = 0.015;

export type BiasLike = { speedMult: number; dirOffsetDeg: number };
export type Perturbation = { speedM: number; dirOffDeg: number; altPertHPa: number };

/** Stationary 1-sigma amplitudes for an ensemble member's AR(1) perturbation,
 *  plus its decorrelation timescale. `tauHours → ∞` (or ≤ 0) makes the
 *  perturbation persistent (one draw held for the whole path — spread grows
 *  ~linearly); `tauHours → 0` makes it per-step white noise (spread grows ~√t).
 *  A finite τ (hours–day) is the realistic middle: correlated over τ, then
 *  mean-reverting — matches how the σ is measured (per-segment scatter). */
export type PerturbSpec = {
    speedSigma: number; // multiplicative speed, fraction (e.g. 0.1 = ±10%)
    dirSigma: number;   // heading offset, degrees
    altSigma: number;   // altitude, hPa
    tauHours: number;
};

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

/** Standard-normal sample (Box–Muller). */
function gauss(): number {
    let u1 = 0;
    let u2 = 0;
    while (u1 === 0) u1 = Math.random();
    while (u2 === 0) u2 = Math.random();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

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

/**
 * Time-aware variant of `integrateBalloonPath`: samples a space-time `WindCube`
 * at each step's actual position AND wall-clock instant (`startTimeMs + elapsed`)
 * instead of a single frozen grid. One continuous integration from the last fix
 * through "now" to the horizon — so the predicted-hindcast and forecast legs
 * share one wind source and join seamlessly. One [lon, lat] point per hour.
 *
 * The ensemble perturbation (`pert`) evolves as an AR(1) / Ornstein–Uhlenbeck
 * process — `x_t = ρ·x_{t-1} + √(1-ρ²)·σ·gauss()`, `ρ = exp(-Δt/τ)` — drawn
 * fresh per call so each member is its own correlated realization. τ→∞ recovers
 * a persistent (constant) perturbation; τ→0 gives per-step white noise; a finite
 * τ is correlated over ~τ then mean-reverts, so the cone grows ~linearly early
 * and damps the runaway at long lead. Zero sigmas ⇒ the deterministic nominal.
 */
export function integrateBalloonPathT(
    startLat: number,
    startLon: number,
    cube: WindCube,
    bias: BiasLike,
    pert: PerturbSpec,
    startTimeMs: number,
    totalHours: number,
): Array<[number, number]> {
    const { speedMult, dirOffsetDeg } = bias;
    const { speedSigma, dirSigma, altSigma, tauHours } = pert;

    const totalSteps = Math.round(totalHours / BALLOON_STEP_HOURS);
    const stepSec = BALLOON_STEP_HOURS * 3600;
    const stepMs = stepSec * 1000;
    const stepsPerHour = Math.round(1 / BALLOON_STEP_HOURS);

    /* AR(1) coefficient for one step. τ ≤ 0 / non-finite ⇒ ρ = 1 (persistent). */
    const rho = tauHours > 0 && Number.isFinite(tauHours)
        ? Math.exp(-BALLOON_STEP_HOURS / tauHours)
        : 1;
    const innov = Math.sqrt(Math.max(0, 1 - rho * rho));
    /* Seed from the stationary distribution so spread is right from step 1. */
    let pSpeed = speedSigma * gauss();
    let pDir = dirSigma * gauss();
    let pAlt = altSigma * gauss();

    let lat = startLat;
    let lon = startLon;
    const path: Array<[number, number]> = [[round4(lon), round4(lat)]];

    for (let s = 1; s <= totalSteps; s++) {
        /* Evolve the perturbation (no-op when ρ = 1, since innov = 0). */
        pSpeed = rho * pSpeed + innov * speedSigma * gauss();
        pDir = rho * pDir + innov * dirSigma * gauss();
        pAlt = rho * pAlt + innov * altSigma * gauss();

        const { u, v } = sampleWind(cube, lat, lon, startTimeMs + s * stepMs);
        const dirRad = ((dirOffsetDeg + pDir) * Math.PI) / 180;
        const cosD = Math.cos(dirRad);
        const sinD = Math.sin(dirRad);
        const k = speedMult * (1 + pSpeed) * (1 + pAlt * ALT_TO_WIND_FACTOR);
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
