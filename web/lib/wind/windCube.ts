import { fetchWindGridHourlySeries, snapPressureHpa, type WindGridBounds } from './fetchWindGrid';
import { windAt, type GfsGrid } from './gfsGrid';
import { assertCanAfford } from './openMeteoBudget';

/**
 * A shared space-time wind field for one forecast compute: a stack of hourly GFS
 * grids over a single bounding box, fetched in ONE Open-Meteo call. Every
 * trajectory — the predicted-hindcast dead-reckon (fix → now), the forward
 * forecast (now → horizon), and every ensemble member — samples this one field,
 * so they all see the same evolving winds. That makes the two regimes continuous
 * (no source switch at "now") and collapses the per-compute request count from
 * ~100 (per-point hourly refetches) to ~1-3 (batched grid series).
 */
export type WindCube = {
    /** Epoch ms of grid hour 0 (floored to the hour). grids[h] = winds at t0Ms + h*stepMs. */
    t0Ms: number;
    stepMs: number;
    grids: GfsGrid[];
    bounds: WindGridBounds;
    gridStep: number;
    levelHpa: number;
};

const HOUR_MS = 3_600_000;

/**
 * Wind at an arbitrary position and instant: bilinear in space (`windAt`) and
 * linear in time between the two bracketing hourly grids. Mirrors the long-gap
 * reconstruction's `windAtHour`, generalized to a wall-clock instant.
 */
export function sampleWind(
    cube: WindCube,
    lat: number,
    lon: number,
    whenMs: number,
): { u: number; v: number } {
    const { grids, t0Ms, stepMs } = cube;
    if (grids.length === 1) return windAt(grids[0], lat, lon);
    const hourFloat = (whenMs - t0Ms) / stepMs;
    const clamped = Math.max(0, Math.min(grids.length - 1, hourFloat));
    const h0 = Math.min(Math.floor(clamped), grids.length - 2);
    const f = clamped - h0;
    const a = windAt(grids[h0], lat, lon);
    const b = windAt(grids[h0 + 1], lat, lon);
    return { u: a.u * (1 - f) + b.u * f, v: a.v * (1 - f) + b.v * f };
}

/**
 * Pick the FINEST grid step whose point count stays within `maxPts`, so a single
 * batched fetch (≤80 pts/request ⇒ 1-2 requests) covers the box. Accuracy-first:
 * small boxes get 1.25-2.5°; only very large stale-gap boxes fall back to 3-4°.
 */
export function chooseGridStep(bounds: WindGridBounds, maxPts = 120): number {
    const spanLat = bounds.latMax - bounds.latMin;
    const spanLon = bounds.lonMax - bounds.lonMin;
    const steps = [1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0];
    for (const step of steps) {
        const n = (Math.round(spanLat / step) + 1) * (Math.round(spanLon / step) + 1);
        if (n <= maxPts) return step;
    }
    return steps[steps.length - 1];
}

/**
 * Fetch the one wind field for a compute, spanning `[startMs, endMs]` over
 * `bounds`. `startMs` is the earliest needed instant (the last GPS fix when
 * dead-reckoning; "now" when GPS is fresh); `endMs` is the forecast horizon end.
 */
export async function fetchWindCube(opts: {
    bounds: WindGridBounds;
    levelHpa: number;
    startMs: number;
    endMs: number;
    gridStep?: number;
}): Promise<WindCube> {
    const levelHpa = snapPressureHpa(opts.levelHpa);
    const gridStep = opts.gridStep ?? chooseGridStep(opts.bounds);
    const t0Ms = Math.floor(opts.startMs / HOUR_MS) * HOUR_MS;
    const spanHours = Math.max(1, (opts.endMs - t0Ms) / HOUR_MS);

    /* Pre-flight call-budget check: the cube needs its WHOLE grid (a partial one
     * has zero-wind holes), so estimate the full cost — ~1 call per grid point,
     * ×(days/14) — and bail before fetching any chunk if it won't fit. Otherwise a
     * tick with little budget left would spend on a few chunks and then abort,
     * wasting them. Mirrors fetchGridHourlySeries' past/forecast-day math so the
     * estimate matches what the per-request meter will actually count. */
    const { latMin, latMax, lonMin, lonMax } = opts.bounds;
    const gridPoints =
        (Math.round((latMax - latMin) / gridStep) + 1) * (Math.round((lonMax - lonMin) / gridStep) + 1);
    const ageH = (Date.now() - t0Ms) / HOUR_MS;
    const forecastDays = Math.min(16, Math.ceil(spanHours / 24) + 2);
    const pastDays = ageH > 6 ? Math.min(92, Math.ceil(ageH / 24) + Math.ceil(spanHours / 24) + 3) : 0;
    const days = Math.max(1, forecastDays + pastDays);
    assertCanAfford(Math.ceil(gridPoints * Math.max(1, days / 14)));

    /* fetchWindGridHourlySeries returns one GfsGrid per hour from t0Ms (caps at
     * 96h, which covers our max fix→horizon span of 72+24). It already computes
     * past_days/forecast_days from the window and batches 80 pts/request. */
    const grids = await fetchWindGridHourlySeries(
        opts.bounds,
        levelHpa,
        gridStep,
        new Date(t0Ms),
        spanHours,
    );
    return { t0Ms, stepMs: HOUR_MS, grids, bounds: opts.bounds, gridStep, levelHpa };
}
