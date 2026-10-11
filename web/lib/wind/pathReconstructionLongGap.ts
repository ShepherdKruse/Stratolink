/**
 * Long-gap path reconstruction (multi-hour GPS-dark segments): a two-filter
 * particle smoother.
 *
 * A forward particle filter runs from fix A toward B and a backward one from B
 * toward A through time-reversed winds, each particle following the cube wind
 * under a bounded AR(1) perturbation (heading offset and speed multiplier as
 * mean-reverting processes, as in the forecast ensemble; altitude offset over
 * the diurnal float model) and WITHOUT any pull toward the far fix. The only
 * weighting inside a filter is the tube penalty (a wind sample read outside
 * the cube's slice boxes is edge-clamped fiction); every few hours a filter
 * whose effective sample size has dropped below half its population is
 * systematically resampled, so neither cloud collapses onto a handful of
 * lineages over a multi-day gap.
 *
 * The two clouds meet at the gap midpoint and overlap for a window of a few
 * steps either side of it: every forward particle is paired with every
 * backward particle within reach, weighted by a Gaussian kernel on their RMS
 * separation over that window (two halves that cross at the midpoint with
 * different headings diverge across the window, so the kernel couples heading
 * as well as position) and by the two particles' residual filter weights. The
 * pair weights ARE the posterior: the drawn bridge is the pair-weighted mean
 * of "forward half + backward half" trajectories, the ellipses are
 * posterior-weighted, and the occupancy footprint is built from pairs
 * resampled by weight. Inside the window a pair's two halves are blended with
 * a smoothstep, so the joined path is continuous in position and velocity —
 * that blend is the only "bridge pull" left.
 *
 * Why not the old forward-only importance sampler: its per-step bridge-pull
 * penalty summed over 600 steps made log-weights span tens of units, so the
 * posterior collapsed onto ONE particle (n_eff 1 at 600 particles, still 2 at
 * 60,000) and the drawn bridge moved 600–850 km (median) run to run on the
 * reference flight's 201 h gap. Pairing two independent clouds of N particles
 * explores N² candidate bridges for the cost of integrating one cloud.
 */

import type { ForecastGpsFix } from './forecastTypes';
import type { BaroSample } from './pathReconstruction';
import { cubeCovers, sampleWind, sampleWindP, type WindCube } from './windCube';

const CFG = {
    /** Particles per filter (forward and backward each). Pairing makes the
     *  posterior N² candidates deep, so this is less about reaching B than
     *  about how many forward lineages land in the backward cloud: on the
     *  reference flight's 201 h gap 600 gave a forward-marginal ESS of ~50 and
     *  a bridge that moved 230 km (median) run to run, 2000 gives ~150 and
     *  65 km for 1.4 s of compute; 5000 (4 s) buys nothing more. The
     *  environment variable `RECON_LONG_GAP_PARTICLES` overrides it. */
    N_PARTICLES: 2000,
    /** Posterior draws behind the drawn line and the occupancy footprint:
     *  bridged trajectories drawn by pair weight from the matched clouds. 2,000
     *  is past the point of diminishing returns — on the reference flight's
     *  201 h gap the line and ribbon from three random 2,000-subsamples of one
     *  10,000 draw differ by 5–13 km / 2–3 km, against 65–103 km / 56–75 km
     *  between independent filter runs. */
    LINE_SAMPLES: 2000,
    /** The drawn line is the TRIMMED LOCAL MEAN of those draws: the per-step
     *  average of the LINE_TRIM_FRAC fraction of sample paths closest (mean
     *  time-matched distance) to the medoid path. A plain posterior mean lands
     *  in the void between modes when the gap's posterior splits (on the 201 h
     *  gap only 0–17 % of samples lie within 300 km of it at the split hours);
     *  the medoid is a real path inside the dominant mode but a discrete pick
     *  that flips between near-tied candidates (draw noise 100–170 km, rerun
     *  worst case ~1,000 km). Averaging the medoid's nearest tenth keeps the
     *  mode (43–45 % of samples within 300 km) at the mean's smoothness and
     *  roughly the mean's rerun stability (67–136 km median, ≤600 km worst). */
    LINE_TRIM_FRAC: 0.10,
    /** Size of the strided subset the medoid is found in (the pairwise distance
     *  matrix is O(subset²)); every draw is then ranked against that medoid. */
    LINE_MEDOID_SUBSET: 1000,
    /** Time-matched path distances sample every n-th step (2 h at 20-min steps). */
    LINE_DISTANCE_STRIDE: 6,
    STEP_MIN: 20,
    /** Per-particle perturbation of the cube wind, as in the forecast ensemble
     *  (`integrateBalloonPathT`): a heading offset and a speed multiplier, each
     *  a mean-reverting AR(1) / Ornstein–Uhlenbeck process with these
     *  STATIONARY 1σ amplitudes and decorrelation time PERTURB_TAU_H, evolved
     *  every step. Bounded by construction — a particle drifts at most a couple
     *  of σ off the wind direction and comes back within ~τ — so a bridge can
     *  no longer fly across or against the flow. (The previous model added an
     *  UNBOUNDED heading random walk of 55°·(1 − directness) per 4 h knot on top
     *  of a fixed offset: its 1σ reached 118° at mid-gap on the reference
     *  flight's 201 h gap, and 7 % of the posterior's steps ran against the
     *  wind.) The speed σ is wider than the forecast's 10 %: it absorbs the
     *  model's speed error over days-long gaps, which is the realistic way a
     *  balloon "loses ground" against the winds — not by crossing them. The
     *  heading σ is the forecast's 12°: on the reference flight it puts the
     *  posterior's step-vs-wind angle at p90 21–27° on every long gap (15° gave
     *  25–32°; the forecast ensemble itself measures 19°). */
    SPEED_SIGMA: 0.25,
    DIR_SIGMA_DEG: 12,
    PERTURB_TAU_H: 18,
    /** Floor on the speed multiplier (a 3σ slow draw must not stall or reverse). */
    SPEED_MULT_MIN: 0.2,
    /** Vertical degree of freedom (multi-level cubes only): each particle
     *  rides its own pressure, the gap's mean pressure (linear between the two
     *  fixes' barometer readings, else the cube's float level) plus an AR(1)
     *  offset that starts at zero at the particle's own fix — the pressure is
     *  measured there — and relaxes to this stationary σ over PRESSURE_TAU_H.
     *  Calibrated on stratolink-3's barometer: within a day the float
     *  pressure scatters by ≈ 1 hPa (the sensor's own noise), across the nine
     *  days of its 201 h gap it drifted 287–290 → 280–282 hPa, so a few-hPa
     *  wander over days with ≈ 8 hPa room. The wind is read at the particle's
     *  pressure (linear between stored levels, clamped to their range), which
     *  replaces the single-level cube's 2 %/km altitude speed scaling. */
    PRESSURE_SIGMA_HPA: 8,
    PRESSURE_TAU_H: 48,
    /** Resampling schedule: a filter is checked for collapse (and resampled)
     *  every ~RESAMPLE_EVERY_HR hours of gap time. */
    RESAMPLE_EVERY_HR: 4,
    ALT_DAY_M: 9750,
    ALT_NIGHT_M: 9450,
    ALT_SIGMA_M: 250,
    SHORT_GAP_MIN: 30,
    /** Mirrored by LONG_GAP_H in scripts/gfs_ingest.py, which lays these gaps'
     *  tube boxes along the forward/backward wind trajectories. */
    LONG_GAP_HR: 6,
    CORRIDOR_NEFF: 40,
    CORRIDOR_MID90_KM: 120,
    FLOAT_ALT_M: 9500,
    TYPICAL_WIND_MS: 20,
    ELLIPSE_FRACS: [0.15, 0.3, 0.5, 0.7, 0.85] as const,
    /** Log-weight cost per wind sample a particle takes OUTSIDE the cube's slice
     *  boxes. Such a sample read an edge-clamped wind, so the step it drove is
     *  fiction: a particle that left the tube must not shape the drawn bridge,
     *  while one grazing the edge for a step or two keeps a usable weight
     *  (e⁻² per step). Inside a filter this is the only weight; resampling at
     *  the resampling checks turns it into "the population stays in the tube". */
    OUTSIDE_CUBE_PENALTY: 2,
    /** Resample a filter at a resampling check when its effective sample size
     *  has fallen below this fraction of the population. */
    RESAMPLE_NEFF_FRAC: 0.5,
    /** Join kernel: σ = this fraction of the tighter cloud's RMS radius at the
     *  meeting step, clamped to [MIN, MAX] km, then doubled until at least
     *  JOIN_MIN_NEFF effective pairs exist (or MAX is reached). Small against
     *  the cloud so the kernel barely widens the posterior; adaptive so a gap
     *  whose two clouds barely overlap still gets a populated bridge. */
    JOIN_SIGMA_FRAC: 0.15,
    JOIN_SIGMA_MIN_KM: 10,
    JOIN_SIGMA_MAX_KM: 300,
    JOIN_MIN_NEFF: 50,
    /** A gap is reported UNEXPLAINED by the winds when the two clouds never
     *  come within reach of each other (no pair inside 4σ even at
     *  JOIN_SIGMA_MAX_KM, so the nearest-neighbour fallback built the bridge) or
     *  when the forward and backward posterior means still miss by more than
     *  this at the meeting step. With the perturbation bounded, the smoother can
     *  no longer invent cross-wind loops to connect A and B; an unexplained gap
     *  is drawn from whatever pairs exist but is flagged (`unexplained`), forced
     *  to corridor mode at low confidence, and carries its honest closure and
     *  n_eff. */
    UNEXPLAINED_CLOSURE_KM: 300,
    /** Overlap window: both filters run this fraction of the gap's steps past
     *  the meeting step (clamped to [MIN, MAX] steps). Pairs are matched on
     *  their RMS separation over ±window and blended across it. */
    JOIN_WINDOW_FRAC: 0.04,
    JOIN_WINDOW_MIN_STEPS: 3,
    JOIN_WINDOW_MAX_STEPS: 24,
};

const R4 = (x: number) => Math.round(x * 1e4) / 1e4;
const R1 = (x: number) => Math.round(x * 10) / 10;
const toRad = (d: number) => (d * Math.PI) / 180;

type Fix = ForecastGpsFix & { alt_m: number };
/** One step of a particle path; `p` is its pressure (hPa) on multi-level cubes. */
export type PathPoint = { lat: number; lon: number; alt: number; p?: number };

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
    /** The smoother's closure error: how far apart the forward and backward
     *  posterior means are at the meeting step before the join ramp blends
     *  them. The drawn bridge itself starts at A and ends at B exactly (the
     *  backward filter is launched from B), so this — not a distance to B — is
     *  the reconstruction-quality signal the old forward sampler's endpoint
     *  miss used to be. */
    endpoint_miss_km: number;
    mid_gap_90_km: number;
    confidence: 'high' | 'medium' | 'low';
    mode: 'line' | 'corridor';
    /** Effective number of matched forward×backward pairs behind the posterior. */
    n_eff: number;
    directness: number;
    net_speed_ms: number;
    short: boolean;
    /** Fraction of the two filters' wind samples that fell outside the cube's
     *  slice boxes (edge-clamped winds), counting every lineage ever integrated.
     *  0 when every particle stayed inside. */
    outside_cube_frac: number;
    /** The same fraction over the bridged trajectories, weighted by posterior
     *  pair weight — i.e. of the samples that actually shape the drawn bridge.
     *  A wide prior cloud (long, low-directness gap) can put many doomed
     *  lineages outside the tube while the bridge itself stays well inside. */
    outside_cube_frac_weighted: number;
    /** True when the winds cannot connect A to B under the perturbation model
     *  (see CFG.UNEXPLAINED_CLOSURE_KM); the gap is then a low-confidence
     *  corridor whatever its spread. */
    unexplained: boolean;
    /** How the drawn `meanPath` was formed: 'trimmed-local-mean' (long gaps,
     *  see CFG.LINE_TRIM_FRAC) or 'straight' (sub-30-min gaps). */
    line_method: 'trimmed-local-mean' | 'straight';
    /** Posterior draws the line was taken from (0 for a straight bridge). */
    line_samples: number;
};

/** The drawn line through a long gap: the per-step mean of the `trimFrac`
 *  fraction of `samples` closest to their medoid, where closeness is the mean
 *  time-matched distance over every `stride`-th step in a per-step local km
 *  frame. The medoid is searched in an evenly strided subset of at most
 *  `medoidSubset` samples (the distance matrix is quadratic); every sample is
 *  then ranked against it. Returns the line, the medoid's sample index and how
 *  many samples were averaged. Pure; exported for tests. */
export function trimmedLocalMean(
    samples: PathPoint[][],
    trimFrac = CFG.LINE_TRIM_FRAC,
    medoidSubset = CFG.LINE_MEDOID_SUBSET,
    stride = CFG.LINE_DISTANCE_STRIDE,
): { path: PathPoint[]; medoid: number; kept: number } {
    const K = samples.length;
    const n1 = samples[0].length;
    const steps: number[] = [];
    for (let s = 0; s < n1; s += Math.max(1, stride)) steps.push(s);
    if (steps[steps.length - 1] !== n1 - 1) steps.push(n1 - 1);
    /* Per-step local frame: km east/north about the samples' mean latitude. */
    const cosRef = steps.map((s) => {
        let lat = 0;
        for (let i = 0; i < K; i++) lat += samples[i][s].lat;
        return Math.cos(toRad(lat / K));
    });
    const kmX = (p: PathPoint, c: number) => p.lon * 111.32 * c;
    const kmY = (p: PathPoint) => p.lat * 111.32;
    /* Medoid within an evenly strided subset (spans the whole draw). */
    const pick = Math.max(1, Math.floor(K / Math.max(1, medoidSubset)));
    const sub: number[] = [];
    for (let i = 0; i < K; i += pick) sub.push(i);
    const M = sub.length;
    const rowSum = new Float64Array(M);
    const xs = new Float64Array(M);
    const ys = new Float64Array(M);
    for (let t = 0; t < steps.length; t++) {
        const s = steps[t];
        const c = cosRef[t];
        for (let a = 0; a < M; a++) { xs[a] = kmX(samples[sub[a]][s], c); ys[a] = kmY(samples[sub[a]][s]); }
        for (let a = 0; a < M; a++) {
            for (let b = a + 1; b < M; b++) {
                const d = Math.hypot(xs[a] - xs[b], ys[a] - ys[b]);
                rowSum[a] += d;
                rowSum[b] += d;
            }
        }
    }
    let best = 0;
    for (let a = 1; a < M; a++) if (rowSum[a] < rowSum[best]) best = a;
    const medoid = sub[best];
    /* Rank every sample by its mean time-matched distance to the medoid path. */
    const toMedoid = new Float64Array(K);
    for (let t = 0; t < steps.length; t++) {
        const s = steps[t];
        const c = cosRef[t];
        const mx = kmX(samples[medoid][s], c);
        const my = kmY(samples[medoid][s]);
        for (let i = 0; i < K; i++) toMedoid[i] += Math.hypot(kmX(samples[i][s], c) - mx, kmY(samples[i][s]) - my);
    }
    const order = Array.from({ length: K }, (_, i) => i).sort((a, b) => toMedoid[a] - toMedoid[b]);
    const kept = Math.min(K, Math.max(3, Math.round(trimFrac * K)));
    const path: PathPoint[] = new Array(n1);
    for (let s = 0; s < n1; s++) {
        let lat = 0;
        let lon = 0;
        let alt = 0;
        for (let k = 0; k < kept; k++) { const q = samples[order[k]][s]; lat += q.lat; lon += q.lon; alt += q.alt; }
        path[s] = { lat: lat / kept, lon: lon / kept, alt: alt / kept };
    }
    return { path, medoid, kept };
}

function particleCount(): number {
    const env = Number(process.env.RECON_LONG_GAP_PARTICLES);
    return Number.isFinite(env) && env >= 10 ? Math.round(env) : CFG.N_PARTICLES;
}

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

/* ── Particle-filter primitives (exported for the unit test) ───────────────── */

/** Effective sample size (Σw)²/Σw² of non-negative, unnormalized weights. */
export function effectiveSampleSize(weights: ArrayLike<number>): number {
    let s = 0;
    let s2 = 0;
    for (let i = 0; i < weights.length; i++) {
        const w = weights[i];
        s += w;
        s2 += w * w;
    }
    return s2 > 0 ? (s * s) / s2 : 0;
}

/** Systematic resampling: `n` ancestor indices drawn from `weights` with ONE
 *  uniform offset `u0` and evenly spaced cumulative targets (u0 + k)/n. The
 *  lowest-variance standard scheme — a particle of normalized weight w gets
 *  ⌊w·n⌋ or ⌈w·n⌉ copies, never more — and equal weights reproduce every
 *  particle exactly once. Indices come out sorted. */
export function systematicResample(
    weights: ArrayLike<number>,
    n = weights.length,
    u0 = Math.random(),
): Int32Array {
    const out = new Int32Array(n);
    let total = 0;
    for (let i = 0; i < weights.length; i++) total += weights[i];
    if (!(total > 0) || weights.length === 0) {
        for (let k = 0; k < n; k++) out[k] = k % Math.max(1, weights.length);
        return out;
    }
    let i = 0;
    let cum = weights[0] / total;
    for (let k = 0; k < n; k++) {
        const target = (u0 + k) / n;
        while (cum < target && i < weights.length - 1) {
            i += 1;
            cum += weights[i] / total;
        }
        out[k] = i;
    }
    return out;
}

/** Blend weight of the backward half at global step `s` for a join at `m`
 *  with overlap window `k`: 0 before the window, 1 after it, a smoothstep in
 *  between — C¹, so the joined path has no kink in position or velocity. */
function joinBlend(s: number, m: number, k: number): number {
    if (s <= m - k) return 0;
    if (s >= m + k) return 1;
    const t = (s - (m - k)) / (2 * k);
    return t * t * (3 - 2 * t);
}

/** One bridged trajectory from a forward half (`fwd[s]` = global step s, run
 *  to `m + k`) and a backward half (`bwd[0]` = fix B, `bwd[nSteps − s]` =
 *  global step s, run back to `m − k`): the forward half before the overlap
 *  window, the backward half after it, and inside the window the smoothstep
 *  blend of the two — continuous in position and velocity, and untouched more
 *  than `k` steps from the meeting step `m`. Length nSteps + 1. */
export function joinHalves(
    fwd: PathPoint[],
    bwd: PathPoint[],
    m: number,
    nSteps: number,
    k: number,
): PathPoint[] {
    const out: PathPoint[] = new Array(nSteps + 1);
    for (let s = 0; s <= nSteps; s++) {
        const a = joinBlend(s, m, k);
        if (a <= 0) out[s] = fwd[s];
        else if (a >= 1) out[s] = bwd[nSteps - s];
        else {
            const f = fwd[s];
            const b = bwd[nSteps - s];
            out[s] = {
                lat: (1 - a) * f.lat + a * b.lat,
                lon: (1 - a) * f.lon + a * b.lon,
                alt: (1 - a) * f.alt + a * b.alt,
                ...(f.p != null && b.p != null ? { p: (1 - a) * f.p + a * b.p } : {}),
            };
        }
    }
    return out;
}

/* ── Posterior geometry ────────────────────────────────────────────────────── */

/** Posterior-weighted 50 % / 90 % error ellipse of a set of [lon, lat]
 *  positions; `weights` are normalized to one here (null ⇒ uniform). */
function computeEllipse(
    positions: Array<[number, number]>,
    weights: ArrayLike<number> | null,
    confidence: 0.5 | 0.9,
): { semi_a_km: number; polygon: Array<[number, number]> } {
    const n = positions.length;
    let wsum = 0;
    for (let i = 0; i < n; i++) wsum += weights ? weights[i] : 1;
    wsum = wsum || 1;
    const wAt = (i: number) => (weights ? weights[i] : 1) / wsum;
    let mLat = 0;
    let mLon = 0;
    for (let i = 0; i < n; i++) {
        mLon += wAt(i) * positions[i][0];
        mLat += wAt(i) * positions[i][1];
    }
    const cosLat = Math.cos(toRad(mLat));
    let sxx = 0;
    let syy = 0;
    let sxy = 0;
    for (let i = 0; i < n; i++) {
        const w = wAt(i);
        const x = (positions[i][0] - mLon) * 111.32 * cosLat;
        const y = (positions[i][1] - mLat) * 111.32;
        sxx += w * x * x;
        syy += w * y * y;
        sxy += w * x * y;
    }
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

/** Altitude through a gap: a barometer sample when one is within 45 min of the
 *  instant, else a diurnal float model — a cosine peaking at 14:00 LOCAL solar
 *  time (a superpressure balloon rides highest in the afternoon). Local time is
 *  UTC + longitude/15 at the sample's longitude (`lon`, default the gap's
 *  midpoint): a transatlantic gap spans eight time zones, and the old fixed
 *  UTC−7 was simply the launch site's zone. */
function buildAltitudeModel(
    tA_ms: number,
    tB_ms: number,
    baroSamples: BaroSample[],
    fallbackLon: number,
): (frac: number, lon?: number) => number {
    const measured = baroSamples.map((s) => ({
        t: new Date(s.time_utc).getTime(),
        alt: s.alt_m,
    }));
    return (frac, lon = fallbackLon) => {
        const t = tA_ms + frac * (tB_ms - tA_ms);
        for (const m of measured) {
            if (Math.abs(t - m.t) < 45 * 60_000) return m.alt;
        }
        const utcHour = (t / 3_600_000) % 24;                       // fractional hours since 00:00 UTC
        const localHour = (((utcHour + lon / 15) % 24) + 24) % 24;
        const dayPhase = Math.cos(((localHour - 14) / 24) * 2 * Math.PI);
        const mid = (CFG.ALT_DAY_M + CFG.ALT_NIGHT_M) / 2;
        const amp = (CFG.ALT_DAY_M - CFG.ALT_NIGHT_M) / 2;
        return mid + amp * dayPhase;
    };
}

/* ── The two filters ───────────────────────────────────────────────────────── */

type ResampleSchedule = { segHours: number; nSegments: number };

/** Resampling checks every ~RESAMPLE_EVERY_HR across the gap (at least one
 *  segment). Both filters run the same schedule from their own fix. */
function resampleSchedule(gapHours: number): ResampleSchedule {
    const nSegments = Math.max(1, Math.round(gapHours / CFG.RESAMPLE_EVERY_HR));
    return { segHours: gapHours / nSegments, nSegments };
}

/** One step of a stationary AR(1) / Ornstein–Uhlenbeck process sampled every
 *  `stepHours`: x ← ρ·x + √(1−ρ²)·σ·ε with ρ = exp(−stepHours/τ). Seeded from
 *  N(0, σ²) the process stays N(0, σ²) at every step (stationary), and its lag-L
 *  autocorrelation is exp(−L·stepHours/τ). Time-reversible, so the backward
 *  filter runs the same process. Pure given `eps`; exported for tests. */
export function ar1Step(x: number, sigma: number, stepHours: number, tauHours: number, eps: number): number {
    const rho = Math.exp(-stepHours / tauHours);
    return rho * x + Math.sqrt(1 - rho * rho) * sigma * eps;
}

export type Particle = {
    lat: number;
    lon: number;
    /** AR(1) speed perturbation: the wind is scaled by 1 + speedPert. */
    speedPert: number;
    /** AR(1) heading offset from the wind direction (degrees). */
    dirOff: number;
    /** AR(1) pressure offset from the gap's mean pressure (hPa; multi-level cubes). */
    pOff: number;
    altOffset: number;
    /** Log-weight accumulated since the last resample (tube penalty only). */
    logW: number;
    /** Wind samples this lineage took outside the cube's slice boxes. */
    outside: number;
    /** Position after each filter step; index 0 is the pinned fix. */
    path: PathPoint[];
};

export type FilterStats = { total: number; outside: number; resamples: number };

/** Residual importance weights of a filter's particles (max-normalized). */
function residualWeights(particles: Particle[]): Float64Array {
    let maxLW = -Infinity;
    for (const p of particles) if (p.logW > maxLW) maxLW = p.logW;
    const w = new Float64Array(particles.length);
    for (let i = 0; i < particles.length; i++) w[i] = Math.exp(particles[i].logW - maxLW);
    return w;
}

/** Systematic resampling of a filter when the tube penalty has collapsed its
 *  weights below RESAMPLE_NEFF_FRAC of the population: survivors are copied
 *  (own path array, weight reset) and the dead lineages dropped. The copies
 *  share their perturbation state but draw their own AR(1) innovations from
 *  the very next step, so they diverge immediately. */
export function resampleIfCollapsed(particles: Particle[], stats: FilterStats): Particle[] {
    const n = particles.length;
    const w = residualWeights(particles);
    if (effectiveSampleSize(w) >= CFG.RESAMPLE_NEFF_FRAC * n) return particles;
    const idx = systematicResample(w, n);
    stats.resamples += 1;
    const out: Particle[] = new Array(n);
    for (let k = 0; k < n; k++) {
        const a = particles[idx[k]];
        out[k] = { ...a, path: a.path.slice(), logW: 0 };
    }
    return out;
}

/** One particle filter from `from` for `nRun` of the gap's `nSteps` steps:
 *  forward in time from A (`dir` = 1) or backward from B through time-reversed
 *  winds (`dir` = −1: a step moves the particle against the wind, to where it
 *  must have come from). Filter step s is global gap step `dir > 0 ? s :
 *  nSteps − s`, so both filters share the altitude model's time fraction and
 *  meet at the same global step. Winds are sampled at the particle's position
 *  at the step's wall-clock end, the forward sampler's convention. */
function runFilter(
    from: Fix,
    cube: WindCube,
    tFrom: number,
    dir: 1 | -1,
    nRun: number,
    nSteps: number,
    gapHours: number,
    altModel: (frac: number, lon?: number) => number,
    schedule: ResampleSchedule,
    n: number,
    stats: FilterStats,
    /** Multi-level cubes: the gap's mean pressure at a time fraction (null ⇒
     *  single level, the wind is read at the cube's level). */
    meanPressure: ((frac: number) => number) | null,
): Particle[] {
    const pMin = cube.levels ? cube.levels[0] : 0;
    const pMax = cube.levels ? cube.levels[cube.levels.length - 1] : 0;
    const pressureAt = (frac: number, off: number) =>
        Math.max(pMin, Math.min(pMax, meanPressure!(frac) + off));
    const stepSec = (gapHours * 3600) / nSteps;
    const stepMs = stepSec * 1000;
    let particles: Particle[] = [];
    for (let i = 0; i < n; i++) {
        particles.push({
            lat: from.lat,
            lon: from.lon,
            /* Seeded from the stationary distribution, like the forecast. */
            speedPert: CFG.SPEED_SIGMA * gauss(),
            dirOff: CFG.DIR_SIGMA_DEG * gauss(),
            pOff: 0,
            altOffset: CFG.ALT_SIGMA_M * gauss(),
            logW: 0,
            outside: 0,
            path: [{
                lat: from.lat,
                lon: from.lon,
                alt: altModel(dir > 0 ? 0 : 1, from.lon),
                ...(meanPressure ? { p: pressureAt(dir > 0 ? 0 : 1, 0) } : {}),
            }],
        });
    }

    const stepHours = stepSec / 3600;
    let seg = 0;                                                    // current resampling segment
    for (let s = 1; s <= nRun; s++) {
        const hour = s * stepHours;                                 // hours since `from`
        /* Resampling check crossed: resample if the tube penalty has collapsed the weights. */
        while (seg + 1 < schedule.nSegments && hour > (seg + 1) * schedule.segHours + 1e-9) {
            particles = resampleIfCollapsed(particles, stats);
            seg += 1;
        }
        const g = dir > 0 ? s : nSteps - s;                         // global step index after the move
        const frac = g / nSteps;
        const whenMs = tFrom + dir * s * stepMs;

        for (const p of particles) {
            const alt = altModel(frac, p.lon) + p.altOffset;
            /* Single level: altitude only scales the wind speed (2 %/km). Multi-
             * level: the particle reads the wind at its own pressure instead. */
            let pres: number | undefined;
            let altScale = 1;
            if (meanPressure) {
                p.pOff = ar1Step(p.pOff, CFG.PRESSURE_SIGMA_HPA, stepHours, CFG.PRESSURE_TAU_H, gauss());
                pres = pressureAt(frac, p.pOff);
            } else {
                altScale = 1 + ((alt - CFG.FLOAT_ALT_M) / 1000) * 0.02;
            }
            stats.total += 1;
            if (!cubeCovers(cube, p.lat, p.lon, whenMs)) {
                p.outside += 1;
                p.logW -= CFG.OUTSIDE_CUBE_PENALTY;
                stats.outside += 1;
            }
            p.speedPert = ar1Step(p.speedPert, CFG.SPEED_SIGMA, stepHours, CFG.PERTURB_TAU_H, gauss());
            p.dirOff = ar1Step(p.dirOff, CFG.DIR_SIGMA_DEG, stepHours, CFG.PERTURB_TAU_H, gauss());
            const { u, v } = pres != null ? sampleWindP(cube, p.lat, p.lon, whenMs, pres) : sampleWind(cube, p.lat, p.lon, whenMs);
            const k = Math.max(CFG.SPEED_MULT_MIN, 1 + p.speedPert) * altScale;
            const dr = toRad(p.dirOff);
            const cosD = Math.cos(dr);
            const sinD = Math.sin(dr);
            const uR = (u * cosD - v * sinD) * k;
            const vR = (u * sinD + v * cosD) * k;
            const cosLat = Math.max(Math.cos(toRad(p.lat)), 0.05);
            p.lat += (dir * vR * stepSec) / 111_320;
            p.lon += (dir * uR * stepSec) / (111_320 * cosLat);
            p.path.push(pres != null ? { lat: p.lat, lon: p.lon, alt, p: pres } : { lat: p.lat, lon: p.lon, alt });
        }
    }
    return particles;
}

/* ── Meeting in the middle ─────────────────────────────────────────────────── */

type Pairs = {
    i: Int32Array;
    j: Int32Array;
    /** Normalized pair weights (sum to one). */
    w: Float64Array;
    /** Forward / backward marginals of `w` (each sums to one). */
    W: Float64Array;
    V: Float64Array;
    nEff: number;
    sigmaKm: number;
    candidates: number;
    /** True when no pair was within reach and the nearest-neighbour fallback
     *  built the pairs (the clouds never met). */
    fallback: boolean;
};

/** Max of an array without spreading it (Math.max(...a) overflows the call
 *  stack past ~100k pairs). */
function maxOf(a: ArrayLike<number>): number {
    let m = -Infinity;
    for (let q = 0; q < a.length; q++) if (a[q] > m) m = a[q];
    return m;
}

/** Pair every forward particle with every backward particle within reach at
 *  the meeting step `m`: weight = residual forward weight × residual backward
 *  weight × Gaussian kernel (σ adaptive) on the two halves' RMS separation
 *  over the overlap window ±`k` steps around `m`. Summing the backward weights
 *  around a forward particle is a kernel density estimate of P(reach B | this
 *  segment at t_m) — the likelihood the old sampler tried to get from an
 *  endpoint miss — and the window makes heading part of the match: halves
 *  that cross at `m` with different headings are far apart at its edges. */
function matchClouds(fwd: Particle[], bwd: Particle[], m: number, nSteps: number, k: number): Pairs {
    const nf = fwd.length;
    const nb = bwd.length;
    const wf = residualWeights(fwd);
    const wb = residualWeights(bwd);
    const latF = new Float64Array(nf);
    const lonF = new Float64Array(nf);
    const latB = new Float64Array(nb);
    const lonB = new Float64Array(nb);
    for (let i = 0; i < nf; i++) {
        latF[i] = fwd[i].path[m].lat;
        lonF[i] = fwd[i].path[m].lon;
    }
    for (let j = 0; j < nb; j++) {
        latB[j] = bwd[j].path[nSteps - m].lat;
        lonB[j] = bwd[j].path[nSteps - m].lon;
    }

    /* Weighted RMS radius of each cloud at the meeting step (km). */
    const spread = (lat: Float64Array, lon: Float64Array, w: Float64Array): number => {
        let ws = 0;
        let mLat = 0;
        let mLon = 0;
        for (let i = 0; i < lat.length; i++) {
            ws += w[i];
            mLat += w[i] * lat[i];
            mLon += w[i] * lon[i];
        }
        if (!(ws > 0)) return 0;
        mLat /= ws;
        mLon /= ws;
        const kx = 111.32 * Math.cos(toRad(mLat));
        let r2 = 0;
        for (let i = 0; i < lat.length; i++) {
            const x = (lon[i] - mLon) * kx;
            const y = (lat[i] - mLat) * 111.32;
            r2 += (w[i] / ws) * (x * x + y * y);
        }
        return Math.sqrt(r2);
    };
    const tight = Math.min(spread(latF, lonF, wf), spread(latB, lonB, wb));
    let sigma = Math.min(CFG.JOIN_SIGMA_MAX_KM, Math.max(CFG.JOIN_SIGMA_MIN_KM, CFG.JOIN_SIGMA_FRAC * tight));

    /* Squared km separation of two positions (equirectangular; ≪ 1° apart). */
    const sep2 = (aLat: number, aLon: number, bLat: number, bLon: number): number => {
        const dy = (bLat - aLat) * 111.32;
        const dx = (bLon - aLon) * 111.32 * Math.cos(toRad(0.5 * (aLat + bLat)));
        return dx * dx + dy * dy;
    };
    /* Mean squared separation of two halves over the overlap window. */
    const windowSep2 = (i: number, j: number): number => {
        const fp = fwd[i].path;
        const bp = bwd[j].path;
        let acc = 0;
        for (let s = m - k; s <= m + k; s++) {
            const f = fp[s];
            const b = bp[nSteps - s];
            acc += sep2(f.lat, f.lon, b.lat, b.lon);
        }
        return acc / (2 * k + 1);
    };

    let I: number[] = [];
    let J: number[] = [];
    let LW: number[] = [];
    let nEff = 0;
    for (;;) {
        I = [];
        J = [];
        LW = [];
        /* Pre-filter on the meeting-step separation (cheap), then score the
         * survivors on the window. A pair 4σ apart at `m` cannot average under
         * 3σ over the window unless the halves cross there, which the window
         * kernel would punish anyway. */
        const cut2 = (4 * sigma) ** 2;
        const inv2s2 = 1 / (2 * sigma * sigma);
        for (let i = 0; i < nf; i++) {
            if (wf[i] < 1e-12) continue;
            const lwf = Math.log(wf[i]);
            for (let j = 0; j < nb; j++) {
                if (wb[j] < 1e-12) continue;
                if (sep2(latF[i], lonF[i], latB[j], lonB[j]) > cut2) continue;
                I.push(i);
                J.push(j);
                LW.push(lwf + Math.log(wb[j]) - windowSep2(i, j) * inv2s2);
            }
        }
        if (LW.length) {
            const top = maxOf(LW);
            nEff = effectiveSampleSize(LW.map((l) => Math.exp(l - top)));
        } else {
            nEff = 0;
        }
        if (nEff >= CFG.JOIN_MIN_NEFF || sigma >= CFG.JOIN_SIGMA_MAX_KM) break;
        sigma = Math.min(CFG.JOIN_SIGMA_MAX_KM, sigma * 2);
    }
    /* Clouds that never come within reach of each other (the winds cannot
     * connect A to B under the model): fall back to each forward particle's
     * nearest backward partner, kernel-weighted without the cutoff, so the
     * smoother still returns a bridge rather than nothing. */
    const fallback = !I.length;
    if (fallback) {
        const inv2s2 = 1 / (2 * sigma * sigma);
        for (let i = 0; i < nf; i++) {
            if (wf[i] < 1e-12) continue;
            let best = -1;
            let bestD2 = Infinity;
            for (let j = 0; j < nb; j++) {
                if (wb[j] < 1e-12) continue;
                const d2 = sep2(latF[i], lonF[i], latB[j], lonB[j]);
                if (d2 < bestD2) {
                    bestD2 = d2;
                    best = j;
                }
            }
            if (best < 0) continue;
            I.push(i);
            J.push(best);
            LW.push(Math.log(wf[i]) + Math.log(wb[best]) - windowSep2(i, best) * inv2s2);
        }
    }

    const maxLW = LW.length ? maxOf(LW) : 0;
    const w = new Float64Array(LW.length);
    let sum = 0;
    for (let q = 0; q < LW.length; q++) {
        w[q] = Math.exp(LW[q] - maxLW);
        sum += w[q];
    }
    const W = new Float64Array(nf);
    const V = new Float64Array(nb);
    for (let q = 0; q < LW.length; q++) {
        w[q] /= sum || 1;
        W[I[q]] += w[q];
        V[J[q]] += w[q];
    }
    return {
        i: Int32Array.from(I),
        j: Int32Array.from(J),
        w,
        W,
        V,
        nEff: effectiveSampleSize(w),
        sigmaKm: sigma,
        candidates: LW.length,
        fallback,
    };
}

/** Reconstruct one long GPS gap with the two-filter smoother and corridor
 *  detection. Same inputs and outputs as the forward sampler it replaces. */
export async function reconstructLongGap(
    A: Fix,
    B: Fix,
    baroSamples: BaroSample[],
    cube: WindCube,
): Promise<LongGapBridgeResult> {
    const t0 = Date.now();
    const tA = new Date(A.time_utc).getTime();
    const tB = new Date(B.time_utc).getTime();
    const gapHours = (tB - tA) / 3_600_000;
    const gapMin = gapHours * 60;
    const nParticles = particleCount();

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
            n_eff: nParticles,
            directness: 1,
            net_speed_ms: 0,
            short: true,
            outside_cube_frac: 0,
            outside_cube_frac_weighted: 0,
            unexplained: false,
            line_method: 'straight',
            line_samples: 0,
        };
    }

    const netKm = distanceKm(A.lat, A.lon, B.lat, B.lon);
    const netSpeed = (netKm * 1000) / (gapHours * 3600);
    const directness = Math.max(0, Math.min(1, netSpeed / CFG.TYPICAL_WIND_MS));

    const nSteps = Math.max(6, Math.round(gapMin / CFG.STEP_MIN));
    const m = Math.floor(nSteps / 2);                               // meeting step (global index)
    const altModel = buildAltitudeModel(tA, tB, baroSamples, (A.lon + B.lon) / 2);
    const schedule = resampleSchedule(gapHours);
    /* Multi-level cube: the particles' mean pressure runs linearly between the
     * two fixes' barometer readings (the cube's float level where a fix has
     * none). */
    const multiLevel = !!cube.levels && cube.levels.length >= 2;
    const pA = A.pressure_hpa ?? cube.levelHpa;
    const pB = B.pressure_hpa ?? cube.levelHpa;
    const meanPressure = multiLevel ? (frac: number) => pA + frac * (pB - pA) : null;

    const statsF: FilterStats = { total: 0, outside: 0, resamples: 0 };
    const statsB: FilterStats = { total: 0, outside: 0, resamples: 0 };
    /* Overlap window: both filters run `kJoin` steps past the meeting step. */
    const kJoin = Math.max(1, Math.min(
        Math.max(CFG.JOIN_WINDOW_MIN_STEPS, Math.min(CFG.JOIN_WINDOW_MAX_STEPS, Math.round(CFG.JOIN_WINDOW_FRAC * nSteps))),
        m - 1,
        nSteps - m - 1,
    ));
    const fwd = runFilter(A, cube, tA, 1, m + kJoin, nSteps, gapHours, altModel, schedule, nParticles, statsF, meanPressure);
    const bwd = runFilter(B, cube, tB, -1, nSteps - m + kJoin, nSteps, gapHours, altModel, schedule, nParticles, statsB, meanPressure);
    const pairs = matchClouds(fwd, bwd, m, nSteps, kJoin);
    const { W, V } = pairs;

    /* Posterior means of the two halves at every step: the forward marginal
     * mean before the window, the backward marginal mean after it, their
     * smoothstep blend inside — exactly what `joinHalves` does per pair, which
     * is linear, so this IS the pair-weighted mean of all bridged
     * trajectories. The two means' distance at the meeting step is the
     * smoother's closure error. */
    const meanF = (s: number): [number, number] => {
        let lat = 0;
        let lon = 0;
        for (let i = 0; i < fwd.length; i++) {
            if (W[i] === 0) continue;
            const p = fwd[i].path[s];
            lat += W[i] * p.lat;
            lon += W[i] * p.lon;
        }
        return [lat, lon];
    };
    const meanB = (s: number): [number, number] => {
        let lat = 0;
        let lon = 0;
        for (let j = 0; j < bwd.length; j++) {
            if (V[j] === 0) continue;
            const p = bwd[j].path[nSteps - s];
            lat += V[j] * p.lat;
            lon += V[j] * p.lon;
        }
        return [lat, lon];
    };
    const [fLat, fLon] = meanF(m);
    const [bLat, bLon] = meanB(m);
    const joinMissKm = distanceKm(fLat, fLon, bLat, bLon);
    const posteriorMean: Array<[number, number]> = [];
    for (let s = 0; s <= nSteps; s++) {
        const a = joinBlend(s, m, kJoin);
        const [lat, lon] = a <= 0 ? meanF(s) : a >= 1 ? meanB(s) : (() => {
            const [fl, fo] = meanF(s);
            const [bl, bo] = meanB(s);
            return [(1 - a) * fl + a * bl, (1 - a) * fo + a * bo];
        })();
        posteriorMean.push([R4(lon), R4(lat)]);
    }

    /* The drawn line. Draw LINE_SAMPLES bridged trajectories by pair weight
     * (the same draws feed the occupancy footprint below) and take the trimmed
     * local mean around their medoid — see CFG.LINE_TRIM_FRAC for why not the
     * posterior mean (sits between modes) or the bare medoid (a coin flip
     * between near-tied paths). Falls back to the posterior mean if no pair
     * could be matched at all. */
    const draw = pairs.w.length ? systematicResample(pairs.w, CFG.LINE_SAMPLES) : new Int32Array(0);
    const samples: PathPoint[][] = new Array(draw.length);
    for (let k = 0; k < draw.length; k++) {
        samples[k] = joinHalves(fwd[pairs.i[draw[k]]].path, bwd[pairs.j[draw[k]]].path, m, nSteps, kJoin);
    }
    const line = samples.length ? trimmedLocalMean(samples) : null;
    const meanPath: Array<[number, number]> = line
        ? line.path.map((p) => [R4(p.lon), R4(p.lat)] as [number, number])
        : posteriorMean;

    /* Coverage: raw over every sample either filter ever took (is the tube wide
     * enough for the prior clouds?), posterior-weighted over the bridged pairs
     * (do the lineages that shape the drawn bridge stay inside? the penalty and
     * resampling make this ~0 unless every lineage left) and the mean path
     * itself (is the drawn line inside the tube?). */
    const totalSamples = statsF.total + statsB.total;
    const outsideSamples = statsF.outside + statsB.outside;
    const outsideFrac = totalSamples ? outsideSamples / totalSamples : 0;
    let outsideWeighted = 0;
    for (let i = 0; i < fwd.length; i++) outsideWeighted += W[i] * fwd[i].outside;
    for (let j = 0; j < bwd.length; j++) outsideWeighted += V[j] * bwd[j].outside;
    outsideWeighted /= nSteps;
    let meanOutside = 0;
    for (let s = 0; s <= nSteps; s++) {
        if (!cubeCovers(cube, meanPath[s][1], meanPath[s][0], tA + (s / nSteps) * gapHours * 3_600_000)) meanOutside += 1;
    }

    /* Posterior-weighted ellipses: forward particles under their marginal up to
     * the meeting step, backward particles under theirs after it. */
    const ellipses: ReconstructionGapEllipse[] = CFG.ELLIPSE_FRACS.map((frac) => {
        const idx = Math.round(frac * nSteps);
        const pos = idx <= m
            ? fwd.map((p) => [p.path[idx].lon, p.path[idx].lat] as [number, number])
            : bwd.map((p) => [p.path[nSteps - idx].lon, p.path[nSteps - idx].lat] as [number, number]);
        const wts = idx <= m ? W : V;
        return {
            frac,
            t_hours: R1(frac * gapHours),
            e50: computeEllipse(pos, wts, 0.5),
            e90: computeEllipse(pos, wts, 0.9),
        };
    });
    const midE90 = ellipses[Math.floor(ellipses.length / 2)].e90.semi_a_km;

    const nEff = pairs.nEff;
    const unexplained = pairs.fallback || joinMissKm > CFG.UNEXPLAINED_CLOSURE_KM;
    const underDetermined = unexplained || nEff < CFG.CORRIDOR_NEFF || midE90 > CFG.CORRIDOR_MID90_KM;
    const confidence: 'high' | 'medium' | 'low' = underDetermined
        ? 'low'
        : midE90 < 40
          ? 'high'
          : 'medium';

    /* Occupancy from bridged trajectories drawn by pair weight (equal weights
     * after the draw), only when the gap is a corridor. */
    let occupancy: OccupancyFootprint | null = null;
    if (underDetermined && samples.length) {
        occupancy = computeOccupancy(samples, new Array(samples.length).fill(1));
    }

    const nEffF = effectiveSampleSize(W);
    const nEffB = effectiveSampleSize(V);
    const log = meanOutside > 0 || unexplained ? console.warn : console.log;
    log(
        `[reconstruction] ${unexplained ? `UNEXPLAINED (${pairs.fallback ? 'clouds never within reach' : 'closure > ' + CFG.UNEXPLAINED_CLOSURE_KM + ' km'}) ` : ''}gap ${A.time_utc} → ${B.time_utc} (${R1(gapHours)} h, ${nParticles}×2 particles): ` +
        `${Math.round(nEff)} effective pairs of ${pairs.candidates} (marginals fwd ${Math.round(nEffF)} / bwd ${Math.round(nEffB)}), ` +
        `join σ ${R1(pairs.sigmaKm)} km, closure ${R1(joinMissKm)} km, resamples fwd ${statsF.resamples} / bwd ${statsB.resamples}; ` +
        `${outsideSamples}/${totalSamples} wind samples outside the cube's slice boxes ` +
        `(${R1(outsideFrac * 100)}% raw, ${R1(outsideWeighted * 100)}% posterior-weighted); ` +
        `line = trimmed local mean of ${line ? line.kept : 0}/${samples.length} draws around the medoid, vertices outside: ${meanOutside}/${nSteps + 1}; ${Date.now() - t0} ms`,
    );

    return {
        meanPath,
        occupancy,
        ellipses,
        dt_hours: R1(gapHours),
        measured_altitude: baroSamples.length > 0,
        endpoint_miss_km: R1(joinMissKm),
        mid_gap_90_km: R1(midE90),
        confidence,
        mode: underDetermined ? 'corridor' : 'line',
        n_eff: Math.round(nEff),
        directness: R1(directness * 100) / 100,
        net_speed_ms: R1(netSpeed),
        short: false,
        outside_cube_frac: Math.round(outsideFrac * 1e4) / 1e4,
        outside_cube_frac_weighted: Math.round(outsideWeighted * 1e4) / 1e4,
        unexplained,
        line_method: 'trimmed-local-mean',
        line_samples: samples.length,
    };
}
