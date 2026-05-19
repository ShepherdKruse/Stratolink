import { boundsFromPoints, fetchWindGrid } from './fetchWindGrid';
import { computeDriftForecast } from './driftForecast';
import { integrateDriftPath, rotateWind, scaleWind, type DriftPoint, type WindModifier } from './driftIntegrate';
import { buildPathCorridorEnvelope } from './predictionCone';
import { buildWindLookup, interpolateWind } from './utils';
import type { WindField, WindVector } from './types';
export type EnsembleMember = {
    id: string;
    label: string;
    points: DriftPoint[];
};

export type DriftEnsembleResult = {
    /** Central GFS trajectory (point-fetched winds along path). */
    points: DriftPoint[];
    ensemble: EnsembleMember[];
    cone: Array<[number, number]>;
    meta: {
        memberCount: number;
        speedSpreadPct: number;
        directionSpreadDeg: number;
        method: string;
    };
};

const SPEED_SPREAD = 0.1;
const DIR_SPREAD_DEG = 15;

function gridCornerWinds(
    lat: number,
    lon: number,
    field: WindField,
    lookup: Map<string, WindVector>,
): [WindVector, WindVector, WindVector, WindVector] {
    const { bounds, gridResolution } = field;
    const li = Math.floor((lat - bounds.latMin) / gridResolution);
    const lj = Math.floor((lon - bounds.lonMin) / gridResolution);
    const get = (i: number, j: number) => lookup.get(`${i},${j}`) ?? { u: 0, v: 0 };
    return [get(li, lj), get(li, lj + 1), get(li + 1, lj), get(li + 1, lj + 1)];
}

function integrateFromGrid(
    startLat: number,
    startLon: number,
    field: WindField,
    lookup: Map<string, WindVector>,
    opts: {
        durationHours: number;
        stepMinutes: number;
        startTime: Date;
        pickCorner: 0 | 1 | 2 | 3;
    },
): DriftPoint[] {
    const { pickCorner } = opts;
    return integrateDriftPath({
        startLat,
        startLon,
        startTime: opts.startTime,
        durationHours: opts.durationHours,
        stepMinutes: opts.stepMinutes,
        sampleWind: (lat, lon) => {
            const corners = gridCornerWinds(lat, lon, field, lookup);
            return corners[pickCorner];
        },
    });
}

function integrateFromGridWithModifier(
    startLat: number,
    startLon: number,
    field: WindField,
    lookup: Map<string, WindVector>,
    modify: WindModifier,
    opts: { durationHours: number; stepMinutes: number; startTime: Date },
): DriftPoint[] {
    return integrateDriftPath({
        startLat,
        startLon,
        startTime: opts.startTime,
        durationHours: opts.durationHours,
        stepMinutes: opts.stepMinutes,
        sampleWind: (lat, lon, when) => {
            const w = interpolateWind(lat, lon, lookup, field.bounds, field.gridResolution);
            return modify(w);
        },
    });
}

/**
 * Mean path + ensemble members (speed/dir perturbations + 4 grid-corner fans).
 * Uncertainty polygon = convex hull of all member points.
 */
export async function computeDriftEnsemble(opts: {
    startLat: number;
    startLon: number;
    pressureHpa: number;
    durationHours?: number;
    stepMinutes?: number;
    refetchEverySteps?: number;
    startTime?: Date;
}): Promise<DriftEnsembleResult> {
    const durationHours = opts.durationHours ?? 24;
    const stepMinutes = opts.stepMinutes ?? 30;
    const startTime = opts.startTime ?? new Date();

    const points = await computeDriftForecast({
        ...opts,
        durationHours,
        stepMinutes,
    });

    const pathPts = points.map((p) => ({ lat: p.lat, lon: p.lon }));
    const gridBounds = boundsFromPoints(pathPts.length ? pathPts : [{ lat: opts.startLat, lon: opts.startLon }], 4);
    const field = await fetchWindGrid(gridBounds, opts.pressureHpa, 1.25);
    const lookup = buildWindLookup(field);

    const gridOpts = { durationHours, stepMinutes, startTime };
    const ensemble: EnsembleMember[] = [
        {
            id: 'speed_lo',
            label: `Wind speed −${SPEED_SPREAD * 100}%`,
            points: integrateFromGridWithModifier(
                opts.startLat,
                opts.startLon,
                field,
                lookup,
                (w) => scaleWind(w, 1 - SPEED_SPREAD),
                gridOpts,
            ),
        },
        {
            id: 'speed_hi',
            label: `Wind speed +${SPEED_SPREAD * 100}%`,
            points: integrateFromGridWithModifier(
                opts.startLat,
                opts.startLon,
                field,
                lookup,
                (w) => scaleWind(w, 1 + SPEED_SPREAD),
                gridOpts,
            ),
        },
        {
            id: 'dir_lo',
            label: `Wind direction −${DIR_SPREAD_DEG}°`,
            points: integrateFromGridWithModifier(
                opts.startLat,
                opts.startLon,
                field,
                lookup,
                (w) => rotateWind(w, -DIR_SPREAD_DEG),
                gridOpts,
            ),
        },
        {
            id: 'dir_hi',
            label: `Wind direction +${DIR_SPREAD_DEG}°`,
            points: integrateFromGridWithModifier(
                opts.startLat,
                opts.startLon,
                field,
                lookup,
                (w) => rotateWind(w, DIR_SPREAD_DEG),
                gridOpts,
            ),
        },
        {
            id: 'grid_sw',
            label: 'Grid cell SW',
            points: integrateFromGrid(opts.startLat, opts.startLon, field, lookup, { ...gridOpts, pickCorner: 0 }),
        },
        {
            id: 'grid_se',
            label: 'Grid cell SE',
            points: integrateFromGrid(opts.startLat, opts.startLon, field, lookup, { ...gridOpts, pickCorner: 1 }),
        },
        {
            id: 'grid_nw',
            label: 'Grid cell NW',
            points: integrateFromGrid(opts.startLat, opts.startLon, field, lookup, { ...gridOpts, pickCorner: 2 }),
        },
        {
            id: 'grid_ne',
            label: 'Grid cell NE',
            points: integrateFromGrid(opts.startLat, opts.startLon, field, lookup, { ...gridOpts, pickCorner: 3 }),
        },
    ];

    const centralPath = points.map((p) => [p.lon, p.lat] as [number, number]);
    const memberPaths = ensemble.map((m) => m.points.map((p) => [p.lon, p.lat] as [number, number]));

    const cone = buildPathCorridorEnvelope(centralPath, memberPaths, 0.08);

    return {
        points,
        ensemble,
        cone,
        meta: {
            memberCount: ensemble.length + 1,
            speedSpreadPct: SPEED_SPREAD * 100,
            directionSpreadDeg: DIR_SPREAD_DEG,
            method: 'GFS grid + speed/direction perturbations (corridor envelope)',
        },
    };
}
