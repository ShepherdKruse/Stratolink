/**
 * Wind-driven particle smoother: reconstruct path between sparse GPS fixes.
 * Ported from reconstruct.js — bridges each inter-fix segment (pinned at both ends).
 */

import { boundsFromPoints, fetchWindGrid, snapPressureHpa } from './fetchWindGrid';
import type { ForecastGpsFix } from './forecastTypes';
import { windAt, windFieldToGfsGrid, type GfsGrid } from './gfsGrid';
import { BALLOON_STEP_HOURS } from './balloonIntegrate';
import { reconstructLongGap } from './pathReconstructionLongGap';

const CFG = {
    N_PARTICLES: 200,
    STEP_HOURS: BALLOON_STEP_HOURS,
    ENDPOINT_SIGMA_KM: 35,
    SPEED_SIGMA: 0.1,
    DIR_SIGMA_DEG: 12,
    ALT_SIGMA_M: 400,
    ALT_TO_WIND_FACTOR: 0.015,
    FLOAT_ALT_M: 9500,
    N_BUNDLE: 24,
    ELLIPSE_FRACS: [0.25, 0.5, 0.75] as const,
    SHORT_GAP_MIN: 20,
    SHOOT_ITERS: 12,
    /** Gaps longer than this use hourly winds + bridge proposal (reconstruct_longgap.js). */
    LONG_GAP_HR: 6,
};

const R4 = (x: number) => Math.round(x * 1e4) / 1e4;
const R1 = (x: number) => Math.round(x * 10) / 10;
const toRad = (d: number) => (d * Math.PI) / 180;

export type BaroSample = { time_utc: string; alt_m: number };

export type ReconstructionGap = {
    from_idx: number;
    to_idx: number;
    dt_hours: number;
    measured_altitude: boolean;
    endpoint_miss_km: number;
    mid_gap_90_km: number;
    confidence: 'high' | 'medium' | 'low';
    short: boolean;
    /** `corridor` when the gap is under-determined (reach region, not a precise line). */
    mode?: 'line' | 'corridor';
    n_eff?: number;
    directness?: number;
    net_speed_ms?: number;
    reach_hull?: Array<[number, number]> | null;
    ellipses?: Array<{
        frac: number;
        t_hours: number;
        e50: { semi_a_km: number; polygon: Array<[number, number]> };
        e90: { semi_a_km: number; polygon: Array<[number, number]> };
    }>;
};

export type ReconstructedTrackPoint = {
    lon: number;
    lat: number;
    time_utc: string;
};

export type PathReconstructionResult = {
    reconstructed_path: Array<[number, number]>;
    /** Same geometry as reconstructed_path with UTC timestamp per point (for timeline scrub). */
    reconstructed_track: ReconstructedTrackPoint[];
    gap_bridges: Array<Array<[number, number]>>;
    gap_reach_hulls: Array<Array<[number, number]>>;
    gaps: ReconstructionGap[];
    compute_ms: number;
};

function appendTimedSegment(
    track: ReconstructedTrackPoint[],
    meanPath: Array<[number, number]>,
    tA_ms: number,
    tB_ms: number,
    skipFirst: boolean,
): void {
    if (meanPath.length === 0) return;
    const nSteps = Math.max(1, meanPath.length - 1);
    const startIdx = skipFirst ? 1 : 0;
    for (let s = startIdx; s < meanPath.length; s++) {
        const frac = s / nSteps;
        track.push({
            lon: meanPath[s][0],
            lat: meanPath[s][1],
            time_utc: new Date(tA_ms + frac * (tB_ms - tA_ms)).toISOString(),
        });
    }
}

type Fix = ForecastGpsFix & { alt_m: number };

type PathPoint = { lat: number; lon: number; alt: number };

function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
    const dLat = toRad(bLat - aLat);
    const dLon = toRad(bLon - aLon);
    const la1 = toRad(aLat);
    const la2 = toRad(bLat);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function bearing(aLat: number, aLon: number, bLat: number, bLon: number): number {
    const y = Math.sin(toRad(bLon - aLon)) * Math.cos(toRad(bLat));
    const x =
        Math.cos(toRad(aLat)) * Math.sin(toRad(bLat)) -
        Math.sin(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.cos(toRad(bLon - aLon));
    return Math.atan2(y, x);
}

function gauss(): number {
    let u1 = 0;
    let u2 = 0;
    while (u1 === 0) u1 = Math.random();
    while (u2 === 0) u2 = Math.random();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

function computeEllipse(
    positions: Array<[number, number]>,
    confidence: 0.5 | 0.9,
): { semi_a_km: number } {
    const n = positions.length;
    const meanLat = positions.reduce((s, [, lat]) => s + lat, 0) / n;
    const meanLon = positions.reduce((s, [lon]) => s + lon, 0) / n;
    const cosLat = Math.cos(toRad(meanLat));
    let sxx = 0;
    let syy = 0;
    let sxy = 0;
    for (const [lon, lat] of positions) {
        const x = (lon - meanLon) * 111.32 * cosLat;
        const y = (lat - meanLat) * 111.32;
        sxx += x * x;
        syy += y * y;
        sxy += x * y;
    }
    sxx /= n;
    syy /= n;
    sxy /= n;
    const chi2 = confidence === 0.5 ? 1.386 : 4.605;
    const tr = sxx + syy;
    const det = sxx * syy - sxy * sxy;
    const disc = Math.max(0, tr * tr / 4 - det);
    const a = Math.sqrt(Math.max(0, tr / 2 + Math.sqrt(disc)) * chi2);
    return { semi_a_km: a };
}

function integrate(
    start: PathPoint,
    gfs: GfsGrid,
    nSteps: number,
    dirSign: 1 | -1,
    params: { speedMult: number; dirOffsetDeg: number },
    altProfile: (frac: number) => number,
): PathPoint[] {
    const { speedMult, dirOffsetDeg } = params;
    const stepSec = CFG.STEP_HOURS * 3600 * dirSign;
    const dr = toRad(dirOffsetDeg);
    const cosD = Math.cos(dr);
    const sinD = Math.sin(dr);

    let lat = start.lat;
    let lon = start.lon;
    const path: PathPoint[] = [{ lat, lon, alt: altProfile(0) }];

    for (let s = 1; s <= nSteps; s++) {
        const frac = s / nSteps;
        const alt = altProfile(frac);
        const altScale = 1 + ((alt - CFG.FLOAT_ALT_M) / 1000) * CFG.ALT_TO_WIND_FACTOR;

        const { u, v } = windAt(gfs, lat, lon);
        const k = speedMult * altScale;
        const uK = u * k;
        const vK = v * k;
        const uR = uK * cosD - vK * sinD;
        const vR = uK * sinD + vK * cosD;

        const cosLat = Math.max(Math.cos(toRad(lat)), 0.05);
        lat += (vR * stepSec) / 111_320;
        lon += (uR * stepSec) / (111_320 * cosLat);
        path.push({ lat, lon, alt });
    }
    return path;
}

function solveShooting(
    A: PathPoint,
    B: PathPoint,
    gfs: GfsGrid,
    nSteps: number,
    altProfile: (frac: number) => number,
): { speedMult: number; dirOffsetDeg: number; miss: number } {
    let speedMult = 1;
    let dirOffsetDeg = 0;
    const DAMP = 0.6;
    let best = { speedMult, dirOffsetDeg, miss: Infinity };

    for (let iter = 0; iter < CFG.SHOOT_ITERS; iter++) {
        const p = integrate(A, gfs, nSteps, 1, { speedMult, dirOffsetDeg }, altProfile);
        const end = p[p.length - 1];
        const miss = distanceKm(B.lat, B.lon, end.lat, end.lon);
        if (miss < best.miss) best = { speedMult, dirOffsetDeg, miss };

        const dReached = distanceKm(A.lat, A.lon, end.lat, end.lon);
        const dTarget = distanceKm(A.lat, A.lon, B.lat, B.lon);
        if (dReached < 1 || miss < 2) break;

        speedMult *= 1 + DAMP * (dTarget / dReached - 1);
        const bReached = bearing(A.lat, A.lon, end.lat, end.lon);
        const bTarget = bearing(A.lat, A.lon, B.lat, B.lon);
        let dB = ((bTarget - bReached) * 180) / Math.PI;
        while (dB > 180) dB -= 360;
        while (dB < -180) dB += 360;
        dirOffsetDeg += DAMP * dB;
    }
    return best;
}

function bridgeGap(
    A: Fix,
    B: Fix,
    gfs: GfsGrid,
    baroSamples: BaroSample[] | null,
): {
    meanPath: Array<[number, number]>;
    dt_hours: number;
    measured_altitude: boolean;
    endpoint_miss_km: number;
    mid_gap_90_km: number;
    confidence: 'high' | 'medium' | 'low';
    short: boolean;
} {
    const tA = new Date(A.time_utc).getTime();
    const tB = new Date(B.time_utc).getTime();
    const gapMin = (tB - tA) / 60_000;
    const nSteps = Math.max(1, Math.round(gapMin / 60 / CFG.STEP_HOURS));

    const altA = A.alt_m ?? CFG.FLOAT_ALT_M;
    const altB = B.alt_m ?? CFG.FLOAT_ALT_M;

    let measured = false;
    let altProfile: (frac: number) => number;

    if (baroSamples && baroSamples.length > 0) {
        measured = true;
        const pts = [
            { t: tA, alt: altA },
            ...baroSamples.map((s) => ({ t: new Date(s.time_utc).getTime(), alt: s.alt_m })),
            { t: tB, alt: altB },
        ].sort((a, b) => a.t - b.t);
        altProfile = (frac) => {
            const t = tA + frac * (tB - tA);
            for (let i = 0; i < pts.length - 1; i++) {
                if (t >= pts[i].t && t <= pts[i + 1].t) {
                    const f = (t - pts[i].t) / (pts[i + 1].t - pts[i].t || 1);
                    return pts[i].alt + f * (pts[i + 1].alt - pts[i].alt);
                }
            }
            return pts[pts.length - 1].alt;
        };
    } else {
        altProfile = (frac) => altA + frac * (altB - altA);
    }

    if (gapMin < CFG.SHORT_GAP_MIN) {
        const p: Array<[number, number]> = [];
        for (let s = 0; s <= nSteps; s++) {
            const f = s / nSteps;
            p.push([R4(A.lon + f * (B.lon - A.lon)), R4(A.lat + f * (B.lat - A.lat))]);
        }
        return {
            meanPath: p,
            dt_hours: R1(gapMin / 60),
            measured_altitude: measured,
            endpoint_miss_km: 0,
            mid_gap_90_km: 0,
            confidence: 'high',
            short: true,
        };
    }

    const start: PathPoint = { lat: A.lat, lon: A.lon, alt: altA };
    const end: PathPoint = { lat: B.lat, lon: B.lon, alt: altB };
    const bias = solveShooting(start, end, gfs, nSteps, altProfile);

    function runCloud(
        from: PathPoint,
        target: PathPoint,
        dirSign: 1 | -1,
    ): { trajs: PathPoint[][]; weights: number[] } {
        const trajs: PathPoint[][] = [];
        const weights: number[] = [];
        for (let i = 0; i < CFG.N_PARTICLES; i++) {
            const params = {
                speedMult: bias.speedMult * (1 + CFG.SPEED_SIGMA * gauss()),
                dirOffsetDeg: bias.dirOffsetDeg + CFG.DIR_SIGMA_DEG * gauss(),
            };
            const aProf = measured
                ? altProfile
                : (() => {
                      const off = CFG.ALT_SIGMA_M * gauss();
                      return (f: number) => altProfile(f) + off;
                  })();
            const p = integrate(from, gfs, nSteps, dirSign, params, aProf);
            const e = p[p.length - 1];
            const miss = distanceKm(target.lat, target.lon, e.lat, e.lon);
            const w = Math.exp(-(miss * miss) / (2 * CFG.ENDPOINT_SIGMA_KM ** 2));
            trajs.push(p);
            weights.push(w);
        }
        return { trajs, weights };
    }

    const fwd = runCloud(start, end, 1);
    const bwd = runCloud(end, start, -1);
    bwd.trajs = bwd.trajs.map((t) => t.slice().reverse());

    function resample(trajs: PathPoint[][], weights: number[]): PathPoint[][] {
        const total = weights.reduce((s, w) => s + w, 0) || 1;
        const cdf: number[] = [];
        let acc = 0;
        for (const w of weights) {
            acc += w / total;
            cdf.push(acc);
        }
        const out: PathPoint[][] = [];
        for (let i = 0; i < trajs.length; i++) {
            const r = Math.random();
            let lo = 0;
            let hi = cdf.length - 1;
            while (lo < hi) {
                const m = (lo + hi) >> 1;
                if (cdf[m] < r) lo = m + 1;
                else hi = m;
            }
            out.push(trajs[lo]);
        }
        return out;
    }

    const pool = resample(fwd.trajs, fwd.weights).concat(resample(bwd.trajs, bwd.weights));

    const meanPath: Array<[number, number]> = [];
    for (let s = 0; s <= nSteps; s++) {
        let mlat = 0;
        let mlon = 0;
        for (const t of pool) {
            mlat += t[s].lat;
            mlon += t[s].lon;
        }
        meanPath.push([R4(mlon / pool.length), R4(mlat / pool.length)]);
    }

    const ellipses = CFG.ELLIPSE_FRACS.map((frac) => {
        const idx = Math.round(frac * nSteps);
        const positions = pool.map((t) => [t[idx].lon, t[idx].lat] as [number, number]);
        return computeEllipse(positions, 0.9);
    });
    const midE90 = ellipses[1]?.semi_a_km ?? 0;

    const endMiss = distanceKm(
        B.lat,
        B.lon,
        meanPath[meanPath.length - 1][1],
        meanPath[meanPath.length - 1][0],
    );
    const confidence = midE90 < 25 ? 'high' : midE90 < 75 ? 'medium' : 'low';

    return {
        meanPath,
        dt_hours: R1(gapMin / 60),
        measured_altitude: measured,
        endpoint_miss_km: R1(endMiss),
        mid_gap_90_km: R1(midE90),
        confidence,
        short: false,
    };
}

function normalizeFixes(fixes: ForecastGpsFix[]): Fix[] {
    return fixes.map((f) => ({
        ...f,
        alt_m: f.alt_m ?? CFG.FLOAT_ALT_M,
    }));
}

/** Reconstruct full observed track with particle bridges between every GPS fix pair. */
export async function computePathReconstruction(opts: {
    fixes: ForecastGpsFix[];
    pressureHpa: number;
    baroSamples?: BaroSample[];
}): Promise<PathReconstructionResult> {
    const t0 = Date.now();
    const fixes = normalizeFixes(opts.fixes);
    if (fixes.length < 2) {
        const single = fixes.map((f) => [R4(f.lon), R4(f.lat)] as [number, number]);
        return {
            reconstructed_path: single,
            reconstructed_track: fixes.map((f) => ({
                lon: R4(f.lon),
                lat: R4(f.lat),
                time_utc: f.time_utc,
            })),
            gap_bridges: [],
            gap_reach_hulls: [],
            gaps: [],
            compute_ms: Date.now() - t0,
        };
    }

    const levelHpa = snapPressureHpa(opts.pressureHpa);
    const marginPts = fixes.map((p) => ({ lat: p.lat, lon: p.lon }));
    const t0ms = new Date(fixes[0].time_utc).getTime();
    const t1ms = new Date(fixes[fixes.length - 1].time_utc).getTime();
    // Track bbox only — gaps are bridged between fixes; do not pad for full mission drift
    // (boundsForForecast with mission span creates 1000+ grid points and Open-Meteo 400s).
    const gridBounds = boundsFromPoints(marginPts, 5);
    const gridStep =
        Math.max(gridBounds.latMax - gridBounds.latMin, gridBounds.lonMax - gridBounds.lonMin) > 22
            ? 3.5
            : 2.5;
    const gridAt = new Date((t0ms + t1ms) / 2);
    const field = await fetchWindGrid(gridBounds, levelHpa, gridStep, gridAt);
    const gfs = windFieldToGfsGrid(field, gridStep);

    const allBaro = opts.baroSamples ?? [];
    const gaps: ReconstructionGap[] = [];
    const gapBridges: Array<Array<[number, number]>> = [];
    const gapReachHulls: Array<Array<[number, number]>> = [];
    const fullPath: Array<[number, number]> = [];
    const reconstructedTrack: ReconstructedTrackPoint[] = [];

    for (let i = 0; i < fixes.length - 1; i++) {
        const A = fixes[i];
        const B = fixes[i + 1];
        const tA = new Date(A.time_utc).getTime();
        const tB = new Date(B.time_utc).getTime();
        const gapHours = (tB - tA) / 3_600_000;
        const baro = allBaro.filter((s) => {
            const t = new Date(s.time_utc).getTime();
            return t > tA && t < tB;
        });

        if (gapHours >= CFG.LONG_GAP_HR) {
            const lg = await reconstructLongGap(A, B, baro, levelHpa);
            gaps.push({
                from_idx: i,
                to_idx: i + 1,
                dt_hours: lg.dt_hours,
                measured_altitude: lg.measured_altitude,
                endpoint_miss_km: lg.endpoint_miss_km,
                mid_gap_90_km: lg.mid_gap_90_km,
                confidence: lg.confidence,
                short: lg.short,
                mode: lg.mode,
                n_eff: lg.n_eff,
                directness: lg.directness,
                net_speed_ms: lg.net_speed_ms,
                reach_hull: lg.reach_hull,
                ellipses: lg.ellipses,
            });
            appendTimedSegment(reconstructedTrack, lg.meanPath, tA, tB, i > 0);
            const seg = [...lg.meanPath];
            if (i > 0) seg.shift();
            fullPath.push(...seg);
            if (!lg.short && lg.meanPath.length >= 2) {
                gapBridges.push(lg.meanPath);
            }
            if (lg.reach_hull && lg.reach_hull.length >= 3) {
                gapReachHulls.push(lg.reach_hull);
            }
            continue;
        }

        const br = bridgeGap(A, B, gfs, baro.length ? baro : null);

        gaps.push({
            from_idx: i,
            to_idx: i + 1,
            dt_hours: br.dt_hours,
            measured_altitude: br.measured_altitude,
            endpoint_miss_km: br.endpoint_miss_km,
            mid_gap_90_km: br.mid_gap_90_km,
            confidence: br.confidence,
            short: br.short,
            mode: 'line',
        });

        appendTimedSegment(reconstructedTrack, br.meanPath, tA, tB, i > 0);
        const seg = [...br.meanPath];
        if (i > 0) seg.shift();
        fullPath.push(...seg);
        if (!br.short && br.meanPath.length >= 2) {
            gapBridges.push(br.meanPath);
        }
    }

    return {
        reconstructed_path: fullPath,
        reconstructed_track: reconstructedTrack,
        gap_bridges: gapBridges,
        gap_reach_hulls: gapReachHulls,
        gaps,
        compute_ms: Date.now() - t0,
    };
}
