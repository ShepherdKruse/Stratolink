import { integrateBalloonPath } from './balloonIntegrate';
import { boundsForForecast, fetchWindGrid, snapPressureHpa } from './fetchWindGrid';
import type { ForecastEllipse, ForecastGpsFix, MonteCarloForecastInput, StratolinkForecast } from './forecastTypes';
import {
    GAP_WIND_MODE,
    gpsGapHours,
    resolveForecastStart,
    STALE_GPS_THRESHOLD_H,
} from './staleGpsExtrapolation';
import { computePathReconstruction } from './pathReconstruction';
import { gfsGridToWindField, windAt, windFieldToGfsGrid, type GfsGrid } from './gfsGrid';

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

function downsampleTrack(track: Array<[number, number]>, maxPts: number): Array<[number, number]> {
    if (track.length <= maxPts) return track;
    const step = Math.ceil(track.length / maxPts);
    const out: Array<[number, number]> = [];
    for (let i = 0; i < track.length; i += step) out.push(track[i]);
    if (out[out.length - 1] !== track[track.length - 1]) out.push(track[track.length - 1]);
    return out;
}

/** Full Monte Carlo pipeline: GFS fetch → bias correction → ensemble → ellipses. */
export async function computeMonteCarloForecast(input: MonteCarloForecastInput): Promise<StratolinkForecast> {
    const t0 = Date.now();
    const totalHours = input.forecastHours ?? CFG.TOTAL_HOURS;
    const levelHpa = snapPressureHpa(input.pressureHpa);
    const nEnsemble = input.nEnsemble ?? CFG.N_ENSEMBLE;

    const lastFix = input.gpsFixes[input.gpsFixes.length - 1];
    if (!lastFix) throw new Error('At least one GPS fix required');

    const marginPts = [
        ...input.gpsFixes.map((p) => ({ lat: p.lat, lon: p.lon })),
        ...input.observedTrackLonLat.map(([lon, lat]) => ({ lat, lon })),
    ];
    const gapH = gpsGapHours(lastFix);
    const boundHours =
        totalHours + (gapH >= STALE_GPS_THRESHOLD_H ? Math.min(gapH, 72) : 0);
    const gridBounds = boundsForForecast(marginPts, input.gpsFixes, boundHours);
    const spanDeg = Math.max(
        gridBounds.latMax - gridBounds.latMin,
        gridBounds.lonMax - gridBounds.lonMin,
    );
    const gridStep = spanDeg > 22 ? 3.5 : 2.5;
    const field = await fetchWindGrid(gridBounds, levelHpa, gridStep);
    const gfs = windFieldToGfsGrid(field, gridStep);

    const bias = computeBias(input.gpsFixes, gfs);

    const reconstruction = await computePathReconstruction({
        fixes: input.gpsFixes,
        pressureHpa: levelHpa,
        baroSamples: input.baroSamples,
    });

    const forecastStart = await resolveForecastStart({
        lastFix,
        gpsFixes: input.gpsFixes,
        observedTrackLonLat: input.observedTrackLonLat,
        pressureHpa: levelHpa,
        bias,
        existingDriftLonLat: input.driftSegmentLonLat,
    });

    const driftSegment =
        forecastStart.implied_drift_lonlat.length >= 2
            ? forecastStart.implied_drift_lonlat
            : (input.driftSegmentLonLat ?? []);

    const ensemble: Array<Array<[number, number]>> = [];
    for (let i = 0; i < nEnsemble; i++) {
        ensemble.push(
            integrateBalloonPath(forecastStart.lat, forecastStart.lon, gfs, bias, {
                speedM: 1 + CFG.SPEED_SIGMA * gauss(),
                dirOffDeg: CFG.DIR_SIGMA_DEG * gauss(),
                altPertHPa: CFG.ALT_SIGMA_HPA * gauss(),
            }, totalHours),
        );
    }

    const nominal = integrateBalloonPath(
        forecastStart.lat,
        forecastStart.lon,
        gfs,
        bias,
        { speedM: 1, dirOffDeg: 0, altPertHPa: 0 },
        totalHours,
    );

    const pathHours = nominal.length - 1;
    const ellipseTimes = CFG.ELLIPSE_TIMES_H.filter((h) => h <= totalHours && h <= pathHours);
    const ellipses = ellipseTimes.map((h) => {
        const positions = ensemble.map((traj) => traj[Math.min(h, traj.length - 1)]);
        return {
            t_hours: h,
            e50: computeEllipse(positions, 0.5),
            e90: computeEllipse(positions, 0.9),
            mean: [
                round4(positions.reduce((s, [lon]) => s + lon, 0) / positions.length),
                round4(positions.reduce((s, [, lat]) => s + lat, 0) / positions.length),
            ] as [number, number],
        };
    });

    const endpoint = nominal[nominal.length - 1];
    const { u: uEnd, v: vEnd } = windAt(gfs, endpoint[1], endpoint[0]);

    return {
        generated_at: new Date().toISOString(),
        forecast_horizon_h: totalHours,
        level_hpa: levelHpa,
        forecast_origin: {
            lat: forecastStart.lat,
            lon: forecastStart.lon,
            alt_m: forecastStart.alt_m,
            time_utc: forecastStart.time_utc,
        },
        stale_gps: forecastStart.stale_gps,
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
            gap_bridges: reconstruction.gap_bridges,
            gap_reach_hulls: reconstruction.gap_reach_hulls,
            reconstruction_gaps: reconstruction.gaps,
        },
        wind_field: {
            lat0: gfs.lat0,
            dLat: gfs.dLat,
            nLat: gfs.nLat,
            lon0: gfs.lon0,
            dLon: gfs.dLon,
            nLon: gfs.nLon,
            U: Array.from(gfs.U).map(round1),
            V: Array.from(gfs.V).map(round1),
        },
        metadata: {
            n_ensemble: nEnsemble,
            step_hours: CFG.STEP_HOURS,
            speed_sigma: CFG.SPEED_SIGMA,
            dir_sigma_deg: CFG.DIR_SIGMA_DEG,
            alt_sigma_hpa: CFG.ALT_SIGMA_HPA,
            compute_ms: Date.now() - t0,
            reconstruction_ms: reconstruction.compute_ms,
            ...(forecastStart.stale_gps ? { gap_wind_mode: GAP_WIND_MODE } : {}),
        },
    };
}
