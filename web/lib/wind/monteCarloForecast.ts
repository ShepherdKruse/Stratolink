import { integrateBalloonPathT } from './balloonIntegrate';
import { boundsForForecast, snapPressureHpa } from './fetchWindGrid';
import type { ForecastEllipse, ForecastGpsFix, MonteCarloForecastInput, StratolinkForecast } from './forecastTypes';
import { GAP_WIND_MODE, gpsGapHours, STALE_GPS_THRESHOLD_H } from './staleGpsExtrapolation';
import { computePathReconstruction, type GapCacheEntry, type PathReconstructionResult } from './pathReconstruction';
import { hindcastInputHash, readGapCache, readStoredHindcast, storeHindcast, writeGapCache } from './hindcastStorage';
import { windAt, type GfsGrid } from './gfsGrid';
import { centerTrack, chooseGridStep, fetchMemberCube, fetchWindCube, listMemberCubes, sampleWind, type WindCube } from './windCube';

const CFG = {
    N_ENSEMBLE: 200,
    STEP_HOURS: 1 / 6,
    TOTAL_HOURS: 24,
    ELLIPSE_TIMES_H: [6, 12, 18, 24] as const,
    SPEED_SIGMA: 0.1,
    DIR_SIGMA_DEG: 12,
    ALT_SIGMA_HPA: 5,
    ALT_TO_WIND_FACTOR: 0.015,
    SPEED_CAP: [0.75, 1.25] as const,
    DIR_CAP_DEG: 25,
    /* Min real (non-frozen) fix pairs before we trust a data-driven sigma; below
     * this we fall back to the fixed defaults rather than let a handful of noisy
     * segments peg the cone to its caps. See TODO in computeBiasFromCube. */
    MIN_SIGMA_SAMPLES: 12,
    /* Decorrelation timescale (h) for the AR(1) ensemble perturbation. Correlated
     * over ~τ then mean-reverts: the forecast cone grows ~linearly within the
     * horizon (τ ≳ horizon) while the multi-day dead-reckon spread stays diffusive
     * rather than ballooning. Tunable; ideally fit from residual autocorrelation. */
    PERTURB_TAU_H: 18,
};

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;
const round1 = (x: number) => Math.round(x * 10) / 10;

export type BiasCorrection = {
    speedMult: number;
    dirOffsetDeg: number;
    nSamples: number;
    rawSpeedMult: number;
    rawDirOffsetDeg: number;
    capped: boolean;
};

export function computeBias(gpsFixes: ForecastGpsFix[], gfs: GfsGrid): BiasCorrection {
    const samples: Array<{ speedMult: number; dirOffset: number }> = [];

    for (let i = 0; i < gpsFixes.length - 1; i++) {
        const a = gpsFixes[i];
        const b = gpsFixes[i + 1];
        const t0 = new Date(a.time_utc).getTime() / 1000;
        const t1 = new Date(b.time_utc).getTime() / 1000;
        const dt = t1 - t0;
        if (dt < 60) continue;
        /* Frozen GPS: a stuck receiver re-sends the identical fix at later
         * timestamps. Zero displacement over nonzero dt ⇒ a bogus 0 m/s speed and
         * an undefined (0°) heading that would pollute the residuals — skip it. */
        if (b.lat === a.lat && b.lon === a.lon) continue;

        const midLat = (a.lat + b.lat) / 2;
        const midLon = (a.lon + b.lon) / 2;
        const cosLat = Math.cos((midLat * Math.PI) / 180);

        const uObs = ((b.lon - a.lon) * 111_320 * cosLat) / dt;
        const vObs = ((b.lat - a.lat) * 111_320) / dt;
        const { u: uGfs, v: vGfs } = windAt(gfs, midLat, midLon);

        const sObs = Math.hypot(uObs, vObs);
        const sGfs = Math.hypot(uGfs, vGfs);
        if (sGfs < 0.5) continue;

        const dirObs = (Math.atan2(vObs, uObs) * 180) / Math.PI;
        const dirGfs = (Math.atan2(vGfs, uGfs) * 180) / Math.PI;
        let dirDiff = dirObs - dirGfs;
        while (dirDiff > 180) dirDiff -= 360;
        while (dirDiff < -180) dirDiff += 360;

        samples.push({ speedMult: sObs / sGfs, dirOffset: dirDiff });
    }

    if (samples.length === 0) {
        return {
            speedMult: 1,
            dirOffsetDeg: 0,
            nSamples: 0,
            rawSpeedMult: 1,
            rawDirOffsetDeg: 0,
            capped: false,
        };
    }

    const speedMult = samples.reduce((s, x) => s + x.speedMult, 0) / samples.length;
    const dirOffsetDeg = samples.reduce((s, x) => s + x.dirOffset, 0) / samples.length;
    const speedClamped = Math.max(CFG.SPEED_CAP[0], Math.min(CFG.SPEED_CAP[1], speedMult));
    const dirClamped = Math.max(-CFG.DIR_CAP_DEG, Math.min(CFG.DIR_CAP_DEG, dirOffsetDeg));

    return {
        speedMult: speedClamped,
        dirOffsetDeg: dirClamped,
        nSamples: samples.length,
        rawSpeedMult: speedMult,
        rawDirOffsetDeg: dirOffsetDeg,
        capped: speedClamped !== speedMult || dirClamped !== dirOffsetDeg,
    };
}

/** Bias + data-driven uncertainty from the cube. Same residual math as
 *  `computeBias`, but each fix pair is compared to the wind at THAT past time and
 *  place (`sampleWind`), not a single snapshot — and we also return the residual
 *  scatter (std-dev), so the ensemble spread reflects how tightly THIS balloon
 *  has been tracking the winds rather than a fixed guess. */
export type CubeBias = BiasCorrection & { speedSigma: number; dirSigma: number };

/* The bias correction is intentionally NEUTRAL: we do NOT fit a speed factor or a
 * direction offset from the fix pairs. For this platform the chord-derived
 * "observed wind" is an unreliable signal — frozen GPS (sparse distinct fixes ⇒
 * chord-vs-arc shortening and a `dt` that mismatches the displacement) and
 * ascent-phase fixes sampled against the float-level winds produce speed ratios
 * scattered ~0.16–60× and a heading offset that swings run-to-run on tiny cube
 * changes (e.g. on stratolink-3 the fit jerked the predicted "now" between 52°E
 * and 108°E). A float balloon advects with the wind, so the honest model is
 * "trust the GFS prediction": hold speedMult = 1 and dirOffset = 0, and let the
 * ensemble explore AROUND the predicted trajectory via fixed, sensible jitters
 * (CFG.SPEED_SIGMA / CFG.DIR_SIGMA_DEG). We still count the clean (moved, ≥5 min)
 * fix pairs purely for observability (`n_samples` in the metadata).
 *
 * (If a better-behaved observation source later warrants a learned bias, re-fit
 * here — see the forecast-uncertainty follow-ups.) */
function neutralBias(gpsFixes: ForecastGpsFix[]): CubeBias {
    let nSamples = 0;
    for (let i = 0; i < gpsFixes.length - 1; i++) {
        const a = gpsFixes[i];
        const b = gpsFixes[i + 1];
        const dt = (new Date(b.time_utc).getTime() - new Date(a.time_utc).getTime()) / 1000;
        if (dt < 300) continue;                          /* <5 min: noisy velocity */
        if (b.lat === a.lat && b.lon === a.lon) continue; /* frozen GPS re-send */
        nSamples += 1;
    }
    return {
        speedMult: 1,
        dirOffsetDeg: 0,
        nSamples,
        rawSpeedMult: 1,
        rawDirOffsetDeg: 0,
        capped: false,
        speedSigma: CFG.SPEED_SIGMA,
        dirSigma: CFG.DIR_SIGMA_DEG,
    };
}

function computeEllipse(positions: Array<[number, number]>, confidence: 0.5 | 0.9): ForecastEllipse {
    const meanLat = positions.reduce((s, [, lat]) => s + lat, 0) / positions.length;
    const meanLon = positions.reduce((s, [lon]) => s + lon, 0) / positions.length;
    const cosLat = Math.cos((meanLat * Math.PI) / 180);

    const xs: number[] = [];
    const ys: number[] = [];
    for (const [lon, lat] of positions) {
        xs.push((lon - meanLon) * 111.32 * cosLat);
        ys.push((lat - meanLat) * 111.32);
    }

    let sxx = 0;
    let syy = 0;
    let sxy = 0;
    for (let i = 0; i < xs.length; i++) {
        sxx += xs[i] * xs[i];
        syy += ys[i] * ys[i];
        sxy += xs[i] * ys[i];
    }
    sxx /= xs.length;
    syy /= ys.length;
    sxy /= xs.length;

    const chi2 = confidence === 0.5 ? 1.386 : 4.605;
    const tr = sxx + syy;
    const det = sxx * syy - sxy * sxy;
    const disc = Math.max(0, (tr * tr) / 4 - det);
    const l1 = tr / 2 + Math.sqrt(disc);
    const l2 = tr / 2 - Math.sqrt(disc);
    const a = Math.sqrt(Math.max(0, l1) * chi2);
    const b = Math.sqrt(Math.max(0, l2) * chi2);
    const theta = 0.5 * Math.atan2(2 * sxy, sxx - syy);

    const coords: Array<[number, number]> = [];
    const N = 64;
    for (let k = 0; k <= N; k++) {
        const t = (k / N) * 2 * Math.PI;
        const xE = a * Math.cos(t);
        const yE = b * Math.sin(t);
        const xR = xE * Math.cos(theta) - yE * Math.sin(theta);
        const yR = xE * Math.sin(theta) + yE * Math.cos(theta);
        coords.push([round4(meanLon + xR / (111.32 * cosLat)), round4(meanLat + yR / 111.32)]);
    }

    return {
        center: [round4(meanLon), round4(meanLat)],
        semi_a_km: round1(a),
        semi_b_km: round1(b),
        theta_deg: round1((theta * 180) / Math.PI),
        polygon: coords,
    };
}

/** Slide an ellipse so it's centered on `center` (the drawn path point) instead
 *  of the ensemble mean — keeps the size/shape (the spread) but pins it to the
 *  path so it reads as "uncertainty around THIS line" rather than floating off
 *  where the wide dead-reckon cloud's centroid happens to land. */
function recenterEllipse(e: ForecastEllipse, center: [number, number]): ForecastEllipse {
    const dLon = center[0] - e.center[0];
    const dLat = center[1] - e.center[1];
    return {
        ...e,
        center: [round4(center[0]), round4(center[1])],
        polygon: e.polygon.map(([x, y]) => [round4(x + dLon), round4(y + dLat)] as [number, number]),
    };
}

function downsampleTrack(track: Array<[number, number]>, maxPts: number): Array<[number, number]> {
    if (track.length <= maxPts) return track;
    const step = Math.ceil(track.length / maxPts);
    const out: Array<[number, number]> = [];
    for (let i = 0; i < track.length; i += step) out.push(track[i]);
    if (out[out.length - 1] !== track[track.length - 1]) out.push(track[track.length - 1]);
    return out;
}

/**
 * A member's trajectory read STRAIGHT from its tube cube's box centers (the
 * pre-integrated nominal the tube was laid along), resampled to one [lon, lat]
 * per hour from `startMs`. This is the exact member path — using it avoids
 * RE-integrating through the cube's 3-hourly boxes, which accumulates a
 * quadrature drift vs the ingest and, for a fast member over a multi-week gap,
 * walks the path out of its own tube and truncates it early. The first point is
 * pinned to the real last fix so it joins the observed track seamlessly. Stops
 * only where the cube's time coverage genuinely ends.
 */
function memberPathFromTube(
    cube: WindCube,
    startMs: number,
    totalHours: number,
    startLon: number,
    startLat: number,
): Array<[number, number]> {
    const centers = centerTrack(cube);
    if (centers.length < 2) return [[round4(startLon), round4(startLat)]];
    const { t0Ms, stepMs } = cube;
    const tEnd = t0Ms + (centers.length - 1) * stepMs;
    const out: Array<[number, number]> = [];
    const steps = Math.max(1, Math.round(totalHours));
    for (let h = 0; h <= steps; h++) {
        if (h === 0) { out.push([round4(startLon), round4(startLat)]); continue; }
        const whenMs = startMs + h * 3_600_000;
        if (whenMs > tEnd + 1) break;
        const f = (whenMs - t0Ms) / stepMs;
        const k0 = Math.max(0, Math.min(centers.length - 2, Math.floor(f)));
        const fr = Math.max(0, Math.min(1, f - k0));
        const a = centers[k0];
        const b = centers[k0 + 1];
        out.push([round4(a[0] + (b[0] - a[0]) * fr), round4(a[1] + (b[1] - a[1]) * fr)]);
    }
    return out;
}

/* Hindcast cache freshness: the trailing gap's analysis winds can still settle
 * for a few hours, so allow a bounded in-place refresh while the last fix is
 * young; once it's older the cached reconstruction is final and reused forever
 * (until a new fix changes the input hash). */
const HINDCAST_REFRESH_WINDOW_H = 6;
const HINDCAST_MIN_REFRESH_INTERVAL_H = 3;

/**
 * The static hindcast, cached by a hash of the GPS fixes. Unchanged fixes ⇒
 * reuse the cached reconstruction (no wind fetch, no re-jitter); a new fix ⇒
 * fresh compute. Returns the reconstruction plus its input hash.
 */
async function resolveReconstruction(
    input: MonteCarloForecastInput,
    levelHpa: number,
    cube: WindCube,
): Promise<{ result: PathReconstructionResult; hash: string }> {
    const hash = hindcastInputHash(input.gpsFixes, levelHpa);
    const lastFix = input.gpsFixes[input.gpsFixes.length - 1];

    const cached = await readStoredHindcast(input.deviceId, hash);
    if (cached) {
        const lastFixAgeH = lastFix
            ? (Date.now() - new Date(lastFix.time_utc).getTime()) / 3_600_000
            : Infinity;
        const cacheAgeH = (Date.now() - new Date(cached.computed_at).getTime()) / 3_600_000;
        const settling =
            lastFixAgeH < HINDCAST_REFRESH_WINDOW_H && cacheAgeH > HINDCAST_MIN_REFRESH_INTERVAL_H;
        if (!settling) {
            return { result: cached, hash };
        }
    }

    /* Cache miss (new/changed fixes). Reuse the per-gap cache so only the recent /
     * trailing gap re-bridges instead of re-running (and re-fetching winds for)
     * the whole flight — appending a fix shouldn't recompute immutable old gaps. */
    const gapRaw = await readGapCache(input.deviceId);
    const gapCache = new Map(Object.entries(gapRaw)) as Map<string, GapCacheEntry>;
    const result = await computePathReconstruction({
        fixes: input.gpsFixes,
        pressureHpa: levelHpa,
        cube,
        baroSamples: input.baroSamples,
        gapCache,
        now: Date.now(),
    });
    /* Always persist gap-cache progress. Only store the whole reconstruction as
     * final when it's complete — a partial (budget-truncated) one must recompute
     * next tick to fill its placeholder gaps. */
    await writeGapCache(input.deviceId, Object.fromEntries(gapCache));
    if (!result.partial) {
        await storeHindcast(input.deviceId, hash, { ...result, computed_at: new Date().toISOString() });
    }
    return { result, hash };
}

/** Full Monte Carlo pipeline: GFS fetch → bias correction → ensemble → ellipses. */
export async function computeMonteCarloForecast(input: MonteCarloForecastInput): Promise<StratolinkForecast> {
    const t0 = Date.now();
    const totalHours = input.forecastHours ?? CFG.TOTAL_HOURS;
    const levelHpa = snapPressureHpa(input.pressureHpa);
    const nEnsemble = input.nEnsemble ?? CFG.N_ENSEMBLE;

    const lastFix = input.gpsFixes[input.gpsFixes.length - 1];
    if (!lastFix) throw new Error('At least one GPS fix required');

    const nowMs = Date.now();
    const fixTimeMs = new Date(lastFix.time_utc).getTime();
    const gapH = gpsGapHours(lastFix);
    const stale = gapH >= STALE_GPS_THRESHOLD_H;

    /* The reconstruction runs over the FULL flight (input.gpsFixes) so the drawn
     * route covers the whole mission. But the forecast cube + bias should reflect
     * only RECENT motion: a continent-spanning full-history bbox would force a
     * coarse grid, and weeks-old fix pairs are stale, time-mismatched bias signal.
     * Use the last RECENT_DAYS of fixes for the cube/bias; fall back to the last
     * handful when the balloon has been quiet longer than that. */
    const RECENT_DAYS = 14;
    const recentCutoffMs = nowMs - RECENT_DAYS * 86_400_000;
    let recentFixes = input.gpsFixes.filter((f) => new Date(f.time_utc).getTime() >= recentCutoffMs);
    if (recentFixes.length < 5) recentFixes = input.gpsFixes.slice(-Math.min(50, input.gpsFixes.length));

    /* The bounding box must contain everywhere the balloon goes: the recent track
     * + (when stale) the dead-reckon out to "now" + the forward horizon. Keep it
     * large enough to contain a long dead-reckon — a member that exits the grid
     * gets edge-clamped (wrong) winds, worse than coarse resolution — and let
     * chooseGridStep pick a coarser step so the single fetch stays within ~1-2
     * requests regardless of box size. */
    const marginPts = recentFixes.map((p) => ({ lat: p.lat, lon: p.lon }));
    const boundHours = totalHours + (stale ? Math.min(gapH, 72) : 0);
    const gridBounds = boundsForForecast(marginPts, recentFixes, boundHours);
    const gridStep = chooseGridStep(gridBounds);

    /* ONE space-time wind field for the whole compute (replaces the snapshot grid
     * + per-point dead-reckon fetches). startMs = the last fix when dead-reckoning,
     * else "now"; endMs = the forecast horizon end. */
    const startMs = stale ? fixTimeMs : nowMs;
    const endMs = nowMs + totalHours * 3_600_000;

    /* Two decoupled fields (scripts/gfs_ingest.py builds both):
     *   - fcCube: small, HOURLY forecast cube whose future leg uses GFS forecast
     *     hours (so the forward forecast evolves), at the finest grid that fits.
     *     Drives the forward forecast, the ensemble, the bias fit and the origin.
     *   - reconCube: full-mission, 3-hourly cube driving only the historical
     *     reconstruction. Both fall back to the full cube / Open-Meteo if absent. */
    const fcCube = await fetchWindCube({
        bounds: gridBounds, levelHpa, startMs, endMs, gridStep, deviceId: input.deviceId, kind: 'forecast',
    });
    const reconCube = await fetchWindCube({
        bounds: gridBounds, levelHpa, startMs, endMs, gridStep, deviceId: input.deviceId, kind: 'reconstruction',
    });

    /* Neutral bias: trust the GFS prediction and jitter the ensemble around it
     * (the chord-derived bias was unreliable here — see neutralBias). */
    const bias = neutralBias(recentFixes);

    const { result: reconstruction, hash: reconstructionHash } = await resolveReconstruction(
        input,
        levelHpa,
        reconCube,
    );

    /* Every member is ONE continuous integration from the last fix (at its real
     * time) through "now" to the horizon — so the predicted-hindcast and forecast
     * legs share one evolving wind field, join with no seam, and the spread grows
     * continuously from ~0 at the fix. Fresh GPS starts at "now" (gap ≈ 0). The
     * per-member perturbation is persistent and uses the DATA-DRIVEN sigma. */
    const startLat = lastFix.lat;
    const startLon = lastFix.lon;
    const spanHours = (stale ? gapH : 0) + totalHours;

    const ZERO_PERT = { speedSigma: 0, dirSigma: 0, altSigma: 0, tauHours: CFG.PERTURB_TAU_H };

    /* Two ways to build the ensemble:
     *   - GEFS members (preferred): one REAL trajectory per member, each integrated
     *     in its OWN wind cube — the member field IS the perturbation, so no
     *     synthetic jitter (bias is neutral, pert = 0). Streamed one member at a
     *     time (binary .slwc keeps that cheap). Flow-dependent, physically-grounded
     *     spread; the nominal is the control member (m00).
     *   - Parametric (fallback): jitter speed/heading around the single GFS field. */
    const memberLabels = input.deviceId ? await listMemberCubes(input.deviceId) : [];
    const ensemble: Array<Array<[number, number]>> = [];
    let nominal!: Array<[number, number]>;
    let windSource = fcCube.source;

    if (memberLabels.length >= 2) {
        let control: Array<[number, number]> | null = null;
        for (const label of memberLabels) {
            const mc = await fetchMemberCube(input.deviceId!, label);
            if (!mc) continue;
            /* A tube member cube already holds the member's exact pre-integrated
             * path as its box-center sequence — read it directly (full, no drift,
             * no early truncation). Only a legacy static member box still needs
             * re-integration. */
            const path = mc.isTube
                ? memberPathFromTube(mc, startMs, spanHours, startLon, startLat)
                : integrateBalloonPathT(startLat, startLon, mc, bias, ZERO_PERT, startMs, spanHours);
            ensemble.push(path);
            if (label === 'm00') control = path;
        }
        if (ensemble.length) {
            nominal = control ?? ensemble[0];
            windSource = 'gefs-ensemble';
        }
    }

    /* Parametric fallback — no GEFS members (or none loaded): jitter speed/heading
     * around the single GFS field. Each integrateBalloonPathT draws its own AR(1)
     * realization internally (correlated over PERTURB_TAU_H). */
    if (!ensemble.length) {
        const pertSpec = {
            speedSigma: bias.speedSigma,
            dirSigma: bias.dirSigma,
            altSigma: CFG.ALT_SIGMA_HPA,
            tauHours: CFG.PERTURB_TAU_H,
        };
        for (let i = 0; i < nEnsemble; i++) {
            ensemble.push(integrateBalloonPathT(startLat, startLon, fcCube, bias, pertSpec, startMs, spanHours));
        }
        nominal = integrateBalloonPathT(startLat, startLon, fcCube, bias, ZERO_PERT, startMs, spanHours);
    }

    /** Hourly index of "now" within each trajectory (= elapsed gap hours); 0 when
     *  GPS is fresh (integration starts at "now"). */
    const nowIdx = stale ? Math.min(Math.round(gapH), nominal.length - 1) : 0;
    const originPt = nominal[nowIdx] ?? [startLon, startLat];
    const nowISO = new Date(nowMs).toISOString();

    /* Coverage-limited: the dead-reckon ran out of wind-cube coverage before it
     * reached "now" (the trajectory truncated — see integrateBalloonPathT). The
     * balloon's current position is then genuinely unknown; the origin is the LAST
     * MODELED point (at fix + modeledHours), not "now", and there's no confident
     * forward forecast. Flagged so the UI can say "modeled to +Xh, then unknown"
     * instead of implying we know where it is. */
    const modeledHours = nominal.length - 1;
    const coverageLimited = stale && modeledHours < Math.round(gapH) - 1;
    const originMs = coverageLimited ? fixTimeMs + modeledHours * 3_600_000 : nowMs;
    const originISO = new Date(originMs).toISOString();

    /* Predicted-hindcast curve = the fix→now portion of the (single, continuous)
     * nominal path. Drawn instead of a straight last-fix→now connector. The
     * forecast leg continues seamlessly from its final point. */
    const predictedHindcast =
        stale && nowIdx >= 1
            ? {
                  path: nominal.slice(0, nowIdx + 1),
                  last_fix_lonlat: [lastFix.lon, lastFix.lat] as [number, number],
                  now_lonlat: [originPt[0], originPt[1]] as [number, number],
                  analysis_boundary_idx: nowIdx,
                  analysis_boundary_time_utc: nowISO,
              }
            : undefined;

    const driftSegment = predictedHindcast?.path ?? input.driftSegmentLonLat ?? [];

    /* A single uncertainty ellipse at the forecast HORIZON (the cone's mouth).
     * The intermediate slices added clutter without much value, so we emit only
     * the final one. recenterEllipse pins it to the nominal endpoint (near-identity
     * since one continuous integration keeps the ensemble mean ≈ nominal).
     * t_hours is relative to "now". */
    const idx = nominal.length - 1;
    const endPositions = ensemble.map((traj) => traj[Math.min(idx, traj.length - 1)]);
    const endCenter = nominal[Math.min(idx, nominal.length - 1)];
    const ellipses = [
        {
            t_hours: idx - nowIdx,
            e50: recenterEllipse(computeEllipse(endPositions, 0.5), endCenter),
            e90: recenterEllipse(computeEllipse(endPositions, 0.9), endCenter),
            mean: [round4(endCenter[0]), round4(endCenter[1])] as [number, number],
        },
    ];

    const endpoint = nominal[nominal.length - 1];
    const { u: uEnd, v: vEnd } = sampleWind(fcCube, endpoint[1], endpoint[0], endMs);

    /* Soft observability check: if many ensemble endpoints sit within one cell of
     * the box edge, the bounds were undersized and trajectories ran on
     * edge-clamped wind. Log it (don't fail). */
    const nearEdge = ensemble.filter((traj) => {
        const [lon, lat] = traj[traj.length - 1];
        return (
            lon <= fcCube.bounds.lonMin + fcCube.gridStep ||
            lon >= fcCube.bounds.lonMax - fcCube.gridStep ||
            lat <= fcCube.bounds.latMin + fcCube.gridStep ||
            lat >= fcCube.bounds.latMax - fcCube.gridStep
        );
    }).length;
    if (nearEdge / Math.max(1, ensemble.length) > 0.2) {
        console.warn(
            `[forecast] ${input.deviceId}: ${nearEdge}/${ensemble.length} ensemble endpoints near grid edge — bounds may be undersized`,
        );
    }

    /* wind_field debug artifact = the "now" slice of the forecast cube. */
    const nowGrid = fcCube.grids[Math.min(nowIdx, fcCube.grids.length - 1)];

    return {
        generated_at: nowISO,
        forecast_horizon_h: totalHours,
        level_hpa: levelHpa,
        forecast_origin: {
            lat: originPt[1],
            lon: originPt[0],
            alt_m: lastFix.alt_m,
            time_utc: originISO,
        },
        stale_gps: stale
            ? {
                  gap_hours: round1(gapH),
                  last_fix_time_utc: lastFix.time_utc,
                  wind_field_time_utc: nowISO,
                  wind_mode: GAP_WIND_MODE,
                  coverage_limited: coverageLimited,
                  modeled_hours: coverageLimited ? modeledHours : undefined,
              }
            : undefined,
        predicted_hindcast: predictedHindcast,
        /* Forecast leg only (now → horizon). The client maps nominal_path onto
         * [origin, origin+horizon] and draws the predicted-hindcast (fix → now)
         * as its own leg — so nominal_path must NOT include the hindcast portion
         * (the full fix→horizon path lives in the ensemble + ellipses). */
        nominal_path: nominal.slice(nowIdx),
        ensemble,
        ellipses,
        endpoint: {
            lat: endpoint[1],
            lon: endpoint[0],
            wind: {
                speed_mps: round1(Math.hypot(uEnd, vEnd)),
                dir_deg: round1(((Math.atan2(-uEnd, -vEnd) * 180) / Math.PI + 360) % 360),
            },
        },
        bias_correction: {
            speed_factor: round1(bias.speedMult * 100) / 100,
            direction_offset_deg: round1(bias.dirOffsetDeg),
            n_samples: bias.nSamples,
            capped: bias.capped,
            raw_speed_factor: round1(bias.rawSpeedMult * 100) / 100,
            raw_direction_offset_deg: round1(bias.rawDirOffsetDeg),
        },
        observed: {
            mission: input.mission,
            device_id: input.deviceId,
            launch: input.launch,
            gps_fixes: input.gpsFixes,
            track: downsampleTrack(input.observedTrackLonLat, 120),
            drift_segment: driftSegment,
            reconstructed_path: reconstruction.reconstructed_path,
            reconstructed_track: reconstruction.reconstructed_track,
            gap_bridges: reconstruction.gap_bridges,
            reconstruction_gaps: reconstruction.gaps,
            reconstruction_input_hash: reconstructionHash,
        },
        wind_field: {
            lat0: nowGrid.lat0,
            dLat: nowGrid.dLat,
            nLat: nowGrid.nLat,
            lon0: nowGrid.lon0,
            dLon: nowGrid.dLon,
            nLon: nowGrid.nLon,
            U: Array.from(nowGrid.U).map(round1),
            V: Array.from(nowGrid.V).map(round1),
        },
        metadata: {
            n_ensemble: ensemble.length,
            step_hours: CFG.STEP_HOURS,
            speed_sigma: Math.round(bias.speedSigma * 1000) / 1000,
            dir_sigma_deg: round1(bias.dirSigma),
            alt_sigma_hpa: CFG.ALT_SIGMA_HPA,
            grid_step_deg: fcCube.gridStep,
            recon_grid_step_deg: reconCube.gridStep,
            wind_source: windSource,
            ...(fcCube.generatedAt ? { wind_cube_generated_at: fcCube.generatedAt } : {}),
            compute_ms: Date.now() - t0,
            reconstruction_ms: reconstruction.compute_ms,
            ...(reconstruction.partial ? { reconstruction_partial: true } : {}),
            ...(stale ? { gap_wind_mode: GAP_WIND_MODE } : {}),
        },
    };
}
