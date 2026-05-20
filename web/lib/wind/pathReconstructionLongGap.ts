/**
 * Long-gap path reconstruction (multi-hour GPS-dark segments).
 * Ported from reconstruct_longgap.js (files v5) — hourly winds, diurnal altitude,
 * bridge proposal, heading walk + directness, occupancy footprint for corridor mode.
 */

import { boundsFromPoints, fetchWindGridHourlySeries, snapPressureHpa } from './fetchWindGrid';
import type { ForecastGpsFix } from './forecastTypes';
import { windAt, type GfsGrid } from './gfsGrid';
import type { BaroSample } from './pathReconstruction';

const CFG = {
    N_PARTICLES: 600,
    STEP_MIN: 20,
    ENDPOINT_SIGMA_KM: 45,
    SPEED_SIGMA: 0.12,
    DIR_SIGMA_DEG: 14,
    HEADING_WALK: true,
    WALK_SEGMENT_HR: 4,
    WALK_STEP_DEG: 55,
    BRIDGE_PULL: 0.55,
    ALT_DAY_M: 9750,
    ALT_NIGHT_M: 9450,
    ALT_SIGMA_M: 250,
    SHORT_GAP_MIN: 30,
    LONG_GAP_HR: 6,
    CORRIDOR_NEFF: 40,
    CORRIDOR_MID90_KM: 120,
    FLOAT_ALT_M: 9500,
    TYPICAL_WIND_MS: 20,
    ELLIPSE_FRACS: [0.15, 0.3, 0.5, 0.7, 0.85] as const,
};

const R4 = (x: number) => Math.round(x * 1e4) / 1e4;
const R1 = (x: number) => Math.round(x * 10) / 10;
const toRad = (d: number) => (d * Math.PI) / 180;

type Fix = ForecastGpsFix & { alt_m: number };
type PathPoint = { lat: number; lon: number; alt: number };

type HeadingKnot = { atHour: number; offsetDeg: number };

export type ReconstructionGapEllipse = {
    frac: number;
    t_hours: number;
    e50: { semi_a_km: number; polygon: Array<[number, number]> };
    e90: { semi_a_km: number; polygon: Array<[number, number]> };
};

export type OccupancyCell = { i: number; j: number; d: number };

/** Sparse grid of P(path passed through cell) for under-determined gaps. */
export type OccupancyFootprint = {
    lat0: number;
    lon0: number;
    dLat: number;
    dLon: number;
    nLat: number;
    nLon: number;
    cells: OccupancyCell[];
};

export type LongGapBridgeResult = {
    meanPath: Array<[number, number]>;
    occupancy: OccupancyFootprint | null;
    ellipses: ReconstructionGapEllipse[];
    dt_hours: number;
    measured_altitude: boolean;
    endpoint_miss_km: number;
    mid_gap_90_km: number;
    confidence: 'high' | 'medium' | 'low';
    mode: 'line' | 'corridor';
    n_eff: number;
    directness: number;
    net_speed_ms: number;
    short: boolean;
};

function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
    const dLat = toRad(bLat - aLat);
    const dLon = toRad(bLon - aLon);
    const la1 = toRad(aLat);
    const la2 = toRad(bLat);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
    return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
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
): { semi_a_km: number; polygon: Array<[number, number]> } {
    const n = positions.length;
    const mLat = positions.reduce((s, [, la]) => s + la, 0) / n;
    const mLon = positions.reduce((s, [lo]) => s + lo, 0) / n;
    const cosLat = Math.cos(toRad(mLat));
    let sxx = 0;
    let syy = 0;
    let sxy = 0;
    for (const [lo, la] of positions) {
        const x = (lo - mLon) * 111.32 * cosLat;
        const y = (la - mLat) * 111.32;
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
    const b = Math.sqrt(Math.max(0, tr / 2 - Math.sqrt(disc)) * chi2);
    const th = 0.5 * Math.atan2(2 * sxy, sxx - syy);
    const poly: Array<[number, number]> = [];
    for (let k = 0; k <= 48; k++) {
        const t = (k / 48) * 2 * Math.PI;
        const xE = a * Math.cos(t);
        const yE = b * Math.sin(t);
        poly.push([
            R4(mLon + (xE * Math.cos(th) - yE * Math.sin(th)) / (111.32 * cosLat)),
            R4(mLat + (xE * Math.sin(th) + yE * Math.cos(th)) / 111.32),
        ]);
    }
    return { semi_a_km: R1(a), polygon: poly };
}

/** Occupancy footprint from full trajectories (replaces convex hull). */
function computeOccupancy(trajs: PathPoint[][], weights: number[]): OccupancyFootprint | null {
    let minLat = Infinity;
    let maxLat = -Infinity;
    let minLon = Infinity;
    let maxLon = -Infinity;
    for (const t of trajs) {
        for (const p of t) {
            if (p.lat < minLat) minLat = p.lat;
            if (p.lat > maxLat) maxLat = p.lat;
            if (p.lon < minLon) minLon = p.lon;
            if (p.lon > maxLon) maxLon = p.lon;
        }
    }
    if (!Number.isFinite(minLat)) return null;

    const padLat = (maxLat - minLat) * 0.04 + 0.1;
    const padLon = (maxLon - minLon) * 0.04 + 0.1;
    minLat -= padLat;
    maxLat += padLat;
    minLon -= padLon;
    maxLon += padLon;
    const spanLat = maxLat - minLat;
    const spanLon = maxLon - minLon;

    let cell = Math.max(spanLat, spanLon) / 44;
    cell = Math.min(0.8, Math.max(0.25, cell));
    const nLat = Math.max(1, Math.ceil(spanLat / cell));
    const nLon = Math.max(1, Math.ceil(spanLon / cell));

    const mass = new Float64Array(nLat * nLon);
    const wsum = weights.reduce((s, w) => s + w, 0) || 1;
    for (let i = 0; i < trajs.length; i++) {
        const w = weights[i] / wsum;
        if (w < 1e-6) continue;
        const seen = new Set<number>();
        for (const p of trajs[i]) {
            const gi = Math.floor((p.lat - minLat) / cell);
            const gj = Math.floor((p.lon - minLon) / cell);
            if (gi < 0 || gi >= nLat || gj < 0 || gj >= nLon) continue;
            const idx = gi * nLon + gj;
            if (!seen.has(idx)) {
                seen.add(idx);
                mass[idx] += w;
            }
        }
    }

    let mx = 0;
    for (const m of mass) {
        if (m > mx) mx = m;
    }
    if (mx <= 0) return null;

    const cells: OccupancyCell[] = [];
    for (let gi = 0; gi < nLat; gi++) {
        for (let gj = 0; gj < nLon; gj++) {
            const d = mass[gi * nLon + gj] / mx;
            if (d >= 0.03) cells.push({ i: gi, j: gj, d: Math.round(d * 100) / 100 });
        }
    }
    return { lat0: R4(minLat), lon0: R4(minLon), dLat: R4(cell), dLon: R4(cell), nLat, nLon, cells };
}

function windAtHour(grids: GfsGrid[], hourFloat: number, lat: number, lon: number): { u: number; v: number } {
    if (grids.length === 1) return windAt(grids[0], lat, lon);
    const h0 = Math.min(Math.floor(hourFloat), grids.length - 2);
    const f = hourFloat - h0;
    const a = windAt(grids[h0], lat, lon);
    const b = windAt(grids[h0 + 1], lat, lon);
    return { u: a.u * (1 - f) + b.u * f, v: a.v * (1 - f) + b.v * f };
}

function buildAltitudeModel(tA_ms: number, tB_ms: number, baroSamples: BaroSample[]): (frac: number) => number {
    const measured = baroSamples.map((s) => ({
        t: new Date(s.time_utc).getTime(),
        alt: s.alt_m,
    }));
    return (frac) => {
        const t = tA_ms + frac * (tB_ms - tA_ms);
        for (const m of measured) {
            if (Math.abs(t - m.t) < 45 * 60_000) return m.alt;
        }
        const localHour = ((new Date(t).getUTCHours() - 7) + 24) % 24;
        const dayPhase = Math.cos(((localHour - 14) / 24) * 2 * Math.PI);
        const mid = (CFG.ALT_DAY_M + CFG.ALT_NIGHT_M) / 2;
        const amp = (CFG.ALT_DAY_M - CFG.ALT_NIGHT_M) / 2;
        return mid + amp * dayPhase;
    };
}

/** Per-particle heading walk — scaled by directness (low net speed → loopier paths). */
function makeHeadingWalk(gapHours: number, directness: number): HeadingKnot[] | null {
    if (!CFG.HEADING_WALK || gapHours < CFG.LONG_GAP_HR) return null;
    const walkScale = Math.max(0, 1 - directness);
    if (walkScale < 0.1) return null;
    const stepDeg = CFG.WALK_STEP_DEG * walkScale;
    const knots: HeadingKnot[] = [];
    const nKnots = Math.max(2, Math.round(gapHours / CFG.WALK_SEGMENT_HR) + 1);
    let offset = CFG.DIR_SIGMA_DEG * gauss();
    for (let i = 0; i < nKnots; i++) {
        knots.push({ atHour: (i / (nKnots - 1)) * gapHours, offsetDeg: offset });
        offset += stepDeg * gauss();
    }
    return knots;
}

function integrateBridge(
    A: Fix,
    B: Fix,
    grids: GfsGrid[],
    nSteps: number,
    gapHours: number,
    altModel: (frac: number) => number,
    pert: {
        speedMult: number;
        dirOffsetDeg: number;
        altOffset: number;
        headingWalk: HeadingKnot[] | null;
    },
): { path: PathPoint[]; logW: number } {
    const stepSec = (gapHours * 3600) / nSteps;

    let headingOffsets: number[];
    if (pert.headingWalk && pert.headingWalk.length) {
        const knots = pert.headingWalk;
        headingOffsets = new Array(nSteps + 1);
        for (let s = 0; s <= nSteps; s++) {
            const hour = (s / nSteps) * gapHours;
            let k0 = knots[0];
            let k1 = knots[knots.length - 1];
            for (let i = 0; i < knots.length - 1; i++) {
                if (hour >= knots[i].atHour && hour <= knots[i + 1].atHour) {
                    k0 = knots[i];
                    k1 = knots[i + 1];
                    break;
                }
            }
            const span = k1.atHour - k0.atHour || 1;
            const f = Math.max(0, Math.min(1, (hour - k0.atHour) / span));
            headingOffsets[s] = toRad(k0.offsetDeg + f * (k1.offsetDeg - k0.offsetDeg));
        }
    } else {
        const dr = toRad(pert.dirOffsetDeg);
        headingOffsets = new Array(nSteps + 1).fill(dr);
    }

    let lat = A.lat;
    let lon = A.lon;
    const path: PathPoint[] = [{ lat, lon, alt: altModel(0) }];
    let logW = 0;

    for (let s = 1; s <= nSteps; s++) {
        const frac = s / nSteps;
        const hourFloat = frac * gapHours;
        const alt = altModel(frac) + pert.altOffset;
        const altScale = 1 + ((alt - CFG.FLOAT_ALT_M) / 1000) * 0.02;

        const { u, v } = windAtHour(grids, hourFloat, lat, lon);
        const k = pert.speedMult * altScale;
        const uK = u * k;
        const vK = v * k;
        const dr = headingOffsets[s];
        const cosD = Math.cos(dr);
        const sinD = Math.sin(dr);
        let uR = uK * cosD - vK * sinD;
        let vR = uK * sinD + vK * cosD;

        const remFrac = 1 - frac;
        if (remFrac > 1e-3) {
            const cosLat = Math.max(Math.cos(toRad(lat)), 0.05);
            const needLat = ((B.lat - lat) * 111_320) / (remFrac * gapHours * 3600);
            const needLon = ((B.lon - lon) * 111_320 * cosLat) / (remFrac * gapHours * 3600);
            const pull = pert.headingWalk
                ? CFG.BRIDGE_PULL * frac ** 2.2
                : CFG.BRIDGE_PULL * frac;
            const nuLat = vR + pull * (needLat - vR);
            const nuLon = uR + pull * (needLon - uR);
            const dv = Math.hypot(nuLon - uR, nuLat - vR);
            logW -= (dv * dv) / (2 * 18 * 18);
            uR = nuLon;
            vR = nuLat;
        }

        const cosLat = Math.max(Math.cos(toRad(lat)), 0.05);
        lat += (vR * stepSec) / 111_320;
        lon += (uR * stepSec) / (111_320 * cosLat);
        path.push({ lat, lon, alt });
    }
    return { path, logW };
}

/** Reconstruct one long GPS gap with hourly winds and corridor detection. */
export async function reconstructLongGap(
    A: Fix,
    B: Fix,
    baroSamples: BaroSample[],
    pressureHpa: number,
): Promise<LongGapBridgeResult> {
    const tA = new Date(A.time_utc).getTime();
    const tB = new Date(B.time_utc).getTime();
    const gapHours = (tB - tA) / 3_600_000;
    const gapMin = gapHours * 60;

    if (gapMin < CFG.SHORT_GAP_MIN) {
        const nSteps = Math.max(2, Math.round(gapMin / CFG.STEP_MIN));
        const p: Array<[number, number]> = [];
        for (let s = 0; s <= nSteps; s++) {
            const f = s / nSteps;
            p.push([R4(A.lon + f * (B.lon - A.lon)), R4(A.lat + f * (B.lat - A.lat))]);
        }
        return {
            meanPath: p,
            occupancy: null,
            ellipses: [],
            dt_hours: R1(gapHours),
            measured_altitude: baroSamples.length > 0,
            endpoint_miss_km: 0,
            mid_gap_90_km: 0,
            confidence: 'high',
            mode: 'line',
            n_eff: CFG.N_PARTICLES,
            directness: 1,
            net_speed_ms: 0,
            short: true,
        };
    }

    const netKm = distanceKm(A.lat, A.lon, B.lat, B.lon);
    const netSpeed = (netKm * 1000) / (gapHours * 3600);
    const directness = Math.max(0, Math.min(1, netSpeed / CFG.TYPICAL_WIND_MS));

    const gridBounds = boundsFromPoints(
        [
            { lat: A.lat, lon: A.lon },
            { lat: B.lat, lon: B.lon },
        ],
        5,
    );
    const spanDeg = Math.max(gridBounds.latMax - gridBounds.latMin, gridBounds.lonMax - gridBounds.lonMin);
    const gridStep = spanDeg > 22 ? 3.5 : 2.5;
    const levelHpa = snapPressureHpa(pressureHpa);
    const grids = await fetchWindGridHourlySeries(
        gridBounds,
        levelHpa,
        gridStep,
        new Date(tA),
        gapHours,
    );

    const nSteps = Math.max(6, Math.round(gapMin / CFG.STEP_MIN));
    const altModel = buildAltitudeModel(tA, tB, baroSamples);
    const trajs: PathPoint[][] = [];
    const logWs: number[] = [];

    for (let i = 0; i < CFG.N_PARTICLES; i++) {
        const pert = {
            speedMult: 1 + CFG.SPEED_SIGMA * gauss(),
            dirOffsetDeg: CFG.DIR_SIGMA_DEG * gauss(),
            altOffset: CFG.ALT_SIGMA_M * gauss(),
            headingWalk: makeHeadingWalk(gapHours, directness),
        };
        const { path, logW } = integrateBridge(A, B, grids, nSteps, gapHours, altModel, pert);
        const end = path[path.length - 1];
        const miss = distanceKm(B.lat, B.lon, end.lat, end.lon);
        const logLik = -(miss * miss) / (2 * CFG.ENDPOINT_SIGMA_KM ** 2);
        trajs.push(path);
        logWs.push(logW + logLik);
    }

    const maxLW = Math.max(...logWs);
    const w = logWs.map((l) => Math.exp(l - maxLW));
    const wsum = w.reduce((s, x) => s + x, 0) || 1;
    const wn = w.map((x) => x / wsum);
    const nEff = 1 / wn.reduce((s, x) => s + x * x, 0);

    const meanPath: Array<[number, number]> = [];
    for (let s = 0; s <= nSteps; s++) {
        let mlat = 0;
        let mlon = 0;
        for (let i = 0; i < trajs.length; i++) {
            mlat += wn[i] * trajs[i][s].lat;
            mlon += wn[i] * trajs[i][s].lon;
        }
        meanPath.push([R4(mlon), R4(mlat)]);
    }

    const ellipses: ReconstructionGapEllipse[] = CFG.ELLIPSE_FRACS.map((frac) => {
        const idx = Math.round(frac * nSteps);
        const pos = trajs.map((t) => [t[idx].lon, t[idx].lat] as [number, number]);
        return {
            frac,
            t_hours: R1(frac * gapHours),
            e50: computeEllipse(pos, 0.5),
            e90: computeEllipse(pos, 0.9),
        };
    });

    const midE90 = ellipses[Math.floor(ellipses.length / 2)].e90.semi_a_km;

    const underDetermined = nEff < CFG.CORRIDOR_NEFF || midE90 > CFG.CORRIDOR_MID90_KM;
    const confidence: 'high' | 'medium' | 'low' = underDetermined
        ? 'low'
        : midE90 < 40
          ? 'high'
          : 'medium';

    const occupancy = underDetermined ? computeOccupancy(trajs, wn) : null;

    const endMiss = distanceKm(
        B.lat,
        B.lon,
        meanPath[meanPath.length - 1][1],
        meanPath[meanPath.length - 1][0],
    );

    return {
        meanPath,
        occupancy,
        ellipses,
        dt_hours: R1(gapHours),
        measured_altitude: baroSamples.length > 0,
        endpoint_miss_km: R1(endMiss),
        mid_gap_90_km: R1(midE90),
        confidence,
        mode: underDetermined ? 'corridor' : 'line',
        n_eff: Math.round(nEff),
        directness: R1(directness * 100) / 100,
        net_speed_ms: R1(netSpeed),
        short: false,
    };
}
