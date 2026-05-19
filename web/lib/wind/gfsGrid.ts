import type { WindField } from './types';
import { buildWindLookup, interpolateWind } from './utils';

export type GfsGrid = {
    lat0: number;
    dLat: number;
    nLat: number;
    lon0: number;
    dLon: number;
    nLon: number;
    U: Float32Array;
    V: Float32Array;
};

export function windAt(gfs: GfsGrid, lat: number, lon: number): { u: number; v: number } {
    const { lat0, dLat, nLat, lon0, dLon, nLon, U, V } = gfs;
    const latMax = lat0 + (nLat - 1) * dLat;
    const lonMax = lon0 + (nLon - 1) * dLon;
    // Clamp to grid edge — returning zero wind outside made trajectories freeze mid-forecast.
    const latC = Math.max(lat0, Math.min(latMax, lat));
    const lonC = Math.max(lon0, Math.min(lonMax, lon));

    const gi = (latC - lat0) / dLat;
    const gj = (lonC - lon0) / dLon;
    const i0 = Math.min(Math.floor(gi), nLat - 2);
    const j0 = Math.min(Math.floor(gj), nLon - 2);
    const fi = gi - i0;
    const fj = gj - j0;
    const id = (i: number, j: number) => i * nLon + j;

    const bl = (arr: Float32Array) =>
        arr[id(i0, j0)] * (1 - fi) * (1 - fj) +
        arr[id(i0 + 1, j0)] * fi * (1 - fj) +
        arr[id(i0, j0 + 1)] * (1 - fi) * fj +
        arr[id(i0 + 1, j0 + 1)] * fi * fj;

    return { u: bl(U), v: bl(V) };
}

/** Resample Open-Meteo wind field onto a regular lat/lon grid for fast integration. */
export function windFieldToGfsGrid(field: WindField, stepDeg?: number): GfsGrid {
    const dLat = stepDeg ?? field.gridResolution;
    const dLon = stepDeg ?? field.gridResolution;
    const { bounds } = field;
    const lat0 = bounds.latMin;
    const lon0 = bounds.lonMin;
    const nLat = Math.max(2, Math.round((bounds.latMax - lat0) / dLat) + 1);
    const nLon = Math.max(2, Math.round((bounds.lonMax - lon0) / dLon) + 1);
    const lookup = buildWindLookup(field);
    const U = new Float32Array(nLat * nLon);
    const V = new Float32Array(nLat * nLon);

    for (let i = 0; i < nLat; i++) {
        const lat = lat0 + i * dLat;
        for (let j = 0; j < nLon; j++) {
            const lon = lon0 + j * dLon;
            const w = interpolateWind(lat, lon, lookup, bounds, field.gridResolution);
            U[i * nLon + j] = w.u;
            V[i * nLon + j] = w.v;
        }
    }

    return { lat0, dLat, nLat, lon0, dLon, nLon, U, V };
}

export function forecastWindBlobToField(
    blob: {
        lat0: number;
        dLat: number;
        nLat: number;
        lon0: number;
        dLon: number;
        nLon: number;
        U: number[];
        V: number[];
    },
    timestamp: string,
    levelHpa: number,
): WindField {
    const gfs: GfsGrid = {
        lat0: blob.lat0,
        dLat: blob.dLat,
        nLat: blob.nLat,
        lon0: blob.lon0,
        dLon: blob.dLon,
        nLon: blob.nLon,
        U: new Float32Array(blob.U),
        V: new Float32Array(blob.V),
    };
    return gfsGridToWindField(gfs, timestamp, levelHpa);
}

export function gfsGridToWindField(gfs: GfsGrid, timestamp: string, levelHpa: number): WindField {
    const grid = [];
    for (let i = 0; i < gfs.nLat; i++) {
        const lat = gfs.lat0 + i * gfs.dLat;
        for (let j = 0; j < gfs.nLon; j++) {
            const lon = gfs.lon0 + j * gfs.dLon;
            const idx = i * gfs.nLon + j;
            grid.push({ lat, lon, wind: { u: gfs.U[idx], v: gfs.V[idx] } });
        }
    }
    return {
        timestamp,
        altitudeBand: levelHpa < 400 ? '15km' : '5km',
        grid,
        gridResolution: gfs.dLat,
        bounds: {
            latMin: gfs.lat0,
            latMax: gfs.lat0 + (gfs.nLat - 1) * gfs.dLat,
            lonMin: gfs.lon0,
            lonMax: gfs.lon0 + (gfs.nLon - 1) * gfs.dLon,
        },
    };
}
