import { integrateBalloonPathT } from './balloonIntegrate';
import { boundsForForecast, snapPressureHpa } from './fetchWindGrid';
import type { ForecastEllipse, ForecastGpsFix, MonteCarloForecastInput, StratolinkForecast } from './forecastTypes';
import { GAP_WIND_MODE, gpsGapHours, STALE_GPS_THRESHOLD_H } from './staleGpsExtrapolation';
import { computePathReconstruction, type PathReconstructionResult } from './pathReconstruction';
import { hindcastInputHash, readStoredHindcast, storeHindcast } from './hindcastStorage';
import { windAt, type GfsGrid } from './gfsGrid';
import { chooseGridStep, fetchWindCube, sampleWind, type WindCube } from './windCube';

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
};

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;
const round1 = (x: number) => Math.round(x * 10) / 10;

function gauss() {
    let u1 = 0;
    let u2 = 0;
    while (u1 === 0) u1 = Math.random();
    while (u2 === 0) u2 = Math.random();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

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

function computeBiasFromCube(gpsFixes: ForecastGpsFix[], cube: WindCube): CubeBias {
    const samples: Array<{ speedMult: number; dirOffset: number }> = [];

    for (let i = 0; i < gpsFixes.length - 1; i++) {
        const a = gpsFixes[i];
        const b = gpsFixes[i + 1];
        const t0 = new Date(a.time_utc).getTime();
        const t1 = new Date(b.time_utc).getTime();
        const dt = (t1 - t0) / 1000;
        if (dt < 300) continue; /* skip <5min pairs — noisy velocity estimate */

        const midLat = (a.lat + b.lat) / 2;
        const midLon = (a.lon + b.lon) / 2;
        const cosLat = Math.cos((midLat * Math.PI) / 180);

        const uObs = ((b.lon - a.lon) * 111_320 * cosLat) / dt;
        const vObs = ((b.lat - a.lat) * 111_320) / dt;
        const { u: uGfs, v: vGfs } = sampleWind(cube, midLat, midLon, (t0 + t1) / 2);

        const sObs = Math.hypot(uObs, vObs);
        const sGfs = Math.hypot(uGfs, vGfs);
        if (sGfs < 1) continue; /* skip near-calm winds — unstable ratio */

        const dirObs = (Math.atan2(vObs, uObs) * 180) / Math.PI;
        const dirGfs = (Math.atan2(vGfs, uGfs) * 180) / Math.PI;
        let dirDiff = dirObs - dirGfs;
        while (dirDiff > 180) dirDiff -= 360;
        while (dirDiff < -180) dirDiff += 360;

        samples.push({ speedMult: sObs / sGfs, dirOffset: dirDiff });
    }

    const fallback: CubeBias = {
        speedMult: 1,
        dirOffsetDeg: 0,
        nSamples: samples.length,
        rawSpeedMult: 1,
        rawDirOffsetDeg: 0,
        capped: false,
        speedSigma: CFG.SPEED_SIGMA,
        dirSigma: CFG.DIR_SIGMA_DEG,
    };
    if (samples.length === 0) return fallback;

    const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
    const std = (xs: number[], m: number) =>
        Math.sqrt(xs.reduce((s, x) => s + (x - m) * (x - m), 0) / xs.length);
    const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));

    const speedMult = mean(samples.map((x) => x.speedMult));
    const dirOffsetDeg = mean(samples.map((x) => x.dirOffset));
    const speedClamped = clamp(speedMult, CFG.SPEED_CAP[0], CFG.SPEED_CAP[1]);
    const dirClamped = clamp(dirOffsetDeg, -CFG.DIR_CAP_DEG, CFG.DIR_CAP_DEG);

    /* Data-driven spread, floored (never zero) and capped (one noisy pair can't
     * blow it up). Falls back to the fixed sigmas when <2 usable pairs. */
    const speedSigma =
        samples.length >= 2
            ? clamp(std(samples.map((x) => x.speedMult), speedMult), 0.05, 0.25)
            : CFG.SPEED_SIGMA;
    const dirSigma =
        samples.length >= 2
            ? clamp(std(samples.map((x) => x.dirOffset), dirOffsetDeg), 6, 30)
            : CFG.DIR_SIGMA_DEG;

    return {
        speedMult: speedClamped,
        dirOffsetDeg: dirClamped,
        nSamples: samples.length,
        rawSpeedMult: speedMult,
        rawDirOffsetDeg: dirOffsetDeg,
        capped: speedClamped !== speedMult || dirClamped !== dirOffsetDeg,
        speedSigma,
        dirSigma,
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

    const result = await computePathReconstruction({
        fixes: input.gpsFixes,
        pressureHpa: levelHpa,
        baroSamples: input.baroSamples,
    });
    await storeHindcast(input.deviceId, hash, { ...result, computed_at: new Date().toISOString() });
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

    /* The bounding box must contain everywhere the balloon goes: the observed
     * track + (when stale) the dead-reckon out to "now" + the forward horizon.
     * Keep it large enough to contain a long dead-reckon — a member that exits
     * the grid gets edge-clamped (wrong) winds, which is worse than coarse
     * resolution — and let chooseGridStep pick a coarser step so the single
     * fetch stays within ~1-2 requests regardless of box size. */
    const marginPts = [
        ...input.gpsFixes.map((p) => ({ lat: p.lat, lon: p.lon })),
        ...input.observedTrackLonLat.map(([lon, lat]) => ({ lat, lon })),
    ];
    const boundHours = totalHours + (stale ? Math.min(gapH, 72) : 0);
    const gridBounds = boundsForForecast(marginPts, input.gpsFixes, boundHours);
    const gridStep = chooseGridStep(gridBounds);

    /* ONE space-time wind field for the whole compute (replaces the snapshot grid
     * + per-point dead-reckon fetches). startMs = the last fix when dead-reckoning,
     * else "now"; endMs = the forecast horizon end. */
    const startMs = stale ? fixTimeMs : nowMs;
    const endMs = nowMs + totalHours * 3_600_000;
    const cube = await fetchWindCube({ bounds: gridBounds, levelHpa, startMs, endMs, gridStep });

    const bias = computeBiasFromCube(input.gpsFixes, cube);

    const { result: reconstruction, hash: reconstructionHash } = await resolveReconstruction(
        input,
        levelHpa,
    );

    /* Every member is ONE continuous integration from the last fix (at its real
     * time) through "now" to the horizon — so the predicted-hindcast and forecast
     * legs share one evolving wind field, join with no seam, and the spread grows
     * continuously from ~0 at the fix. Fresh GPS starts at "now" (gap ≈ 0). The
     * per-member perturbation is persistent and uses the DATA-DRIVEN sigma. */
    const startLat = lastFix.lat;
    const startLon = lastFix.lon;
    const spanHours = (stale ? gapH : 0) + totalHours;

    const ensemble: Array<Array<[number, number]>> = [];
    for (let i = 0; i < nEnsemble; i++) {
        ensemble.push(
            integrateBalloonPathT(
                startLat,
                startLon,
                cube,
                bias,
                {
                    speedM: 1 + bias.speedSigma * gauss(),
                    dirOffDeg: bias.dirSigma * gauss(),
                    altPertHPa: CFG.ALT_SIGMA_HPA * gauss(),
                },
                startMs,
                spanHours,
            ),
        );
    }

    const nominal = integrateBalloonPathT(
        startLat,
        startLon,
        cube,
        bias,
        { speedM: 1, dirOffDeg: 0, altPertHPa: 0 },
        startMs,
        spanHours,
    );

    /** Hourly index of "now" within each trajectory (= elapsed gap hours); 0 when
     *  GPS is fresh (integration starts at "now"). */
    const nowIdx = stale ? Math.min(Math.round(gapH), nominal.length - 1) : 0;
    const originPt = nominal[nowIdx] ?? [startLon, startLat];
    const nowISO = new Date(nowMs).toISOString();

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

    /* Uncertainty ellipses sliced across the WHOLE trajectory (fix → horizon).
     * recenterEllipse pins each to the nominal path point — now near-identity
     * since one continuous integration keeps the ensemble mean ≈ nominal.
     * t_hours is relative to "now" (negative over the predicted-hindcast leg). */
    const fullSpan = nominal.length - 1;
    const sliceIdxs = Array.from(
        new Set(
            [0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1].map((f) =>
                Math.min(fullSpan, Math.max(1, Math.round(f * fullSpan))),
            ),
        ),
    ).sort((a, b) => a - b);
    const ellipses = sliceIdxs.map((idx) => {
        const positions = ensemble.map((traj) => traj[Math.min(idx, traj.length - 1)]);
        const center = nominal[Math.min(idx, nominal.length - 1)];
        return {
            t_hours: idx - nowIdx,
            e50: recenterEllipse(computeEllipse(positions, 0.5), center),
            e90: recenterEllipse(computeEllipse(positions, 0.9), center),
            mean: [round4(center[0]), round4(center[1])] as [number, number],
        };
    });

    const endpoint = nominal[nominal.length - 1];
    const { u: uEnd, v: vEnd } = sampleWind(cube, endpoint[1], endpoint[0], endMs);

    /* Soft observability check: if many ensemble endpoints sit within one cell of
     * the box edge, the bounds were undersized and trajectories ran on
     * edge-clamped wind. Log it (don't fail). */
    const nearEdge = ensemble.filter((traj) => {
        const [lon, lat] = traj[traj.length - 1];
        return (
            lon <= cube.bounds.lonMin + cube.gridStep ||
            lon >= cube.bounds.lonMax - cube.gridStep ||
            lat <= cube.bounds.latMin + cube.gridStep ||
            lat >= cube.bounds.latMax - cube.gridStep
        );
    }).length;
    if (nearEdge / Math.max(1, ensemble.length) > 0.2) {
        console.warn(
            `[forecast] ${input.deviceId}: ${nearEdge}/${ensemble.length} ensemble endpoints near grid edge — bounds may be undersized`,
        );
    }

    /* wind_field debug artifact = the "now" slice of the cube (not a frozen grid). */
    const nowGrid = cube.grids[Math.min(nowIdx, cube.grids.length - 1)];

    return {
        generated_at: nowISO,
        forecast_horizon_h: totalHours,
        level_hpa: levelHpa,
        forecast_origin: {
            lat: originPt[1],
            lon: originPt[0],
            alt_m: lastFix.alt_m,
            time_utc: nowISO,
        },
        stale_gps: stale
            ? {
                  gap_hours: round1(gapH),
                  last_fix_time_utc: lastFix.time_utc,
                  wind_field_time_utc: nowISO,
                  wind_mode: GAP_WIND_MODE,
              }
            : undefined,
        predicted_hindcast: predictedHindcast,
        nominal_path: nominal,
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
            n_ensemble: nEnsemble,
            step_hours: CFG.STEP_HOURS,
            speed_sigma: Math.round(bias.speedSigma * 1000) / 1000,
            dir_sigma_deg: round1(bias.dirSigma),
            alt_sigma_hpa: CFG.ALT_SIGMA_HPA,
            grid_step_deg: gridStep,
            compute_ms: Date.now() - t0,
            reconstruction_ms: reconstruction.compute_ms,
            ...(stale ? { gap_wind_mode: GAP_WIND_MODE } : {}),
        },
    };
}
