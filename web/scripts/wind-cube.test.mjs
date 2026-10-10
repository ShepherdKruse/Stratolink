/**
 * Wind-cube decode + coverage semantics, against a hand-packed .slwc so the test
 * needs no NOAA, no numpy and no network:
 *   - v3 tube header (`dims`): per-slice box sizes decode and sample correctly
 *   - `cubeCovers` tests the bracketing slice boxes, not the tube's union bounds
 *   - `integrateBalloonPathT` stops where a path leaves its slice box
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { bracketSlices, cubeCovers, fetchWindCube, sampleWind } from '../lib/wind/windCube.ts';
import { integrateBalloonPathT } from '../lib/wind/balloonIntegrate.ts';

const HOUR = 3_600_000;

/** Pack grids the way scripts/gfs_ingest.py `pack_cube` does:
 *  [uint32 LE headerLen][header JSON, padded to 4 bytes][int16 U then V per grid]. */
function packCube(header, grids, scale = 10) {
    const hb = Buffer.from(JSON.stringify({ ...header, scale }), 'utf8');
    const pad = ((-(4 + hb.length)) % 4 + 4) % 4;        // JS % keeps the sign; Python's does not
    const head = Buffer.alloc(4);
    head.writeUInt32LE(hb.length + pad, 0);
    const parts = [head, hb, Buffer.alloc(pad, 0x20)];
    for (const g of grids) {
        for (const comp of ['U', 'V']) {
            const buf = Buffer.alloc(g[comp].length * 2);
            g[comp].forEach((x, i) => buf.writeInt16LE(Math.round(x * scale), i * 2));
            parts.push(buf);
        }
    }
    return Buffer.concat(parts);
}

/** A 1° box of n×n points at (lat0, lon0) with uniform winds. */
function box(lat0, lon0, n, u, v) {
    return { lat0, lon0, nLat: n, nLon: n, U: new Array(n * n).fill(u), V: new Array(n * n).fill(v) };
}

function writeCube(dir, name, header, grids) {
    writeFileSync(join(dir, `${name}.slwc`), packCube(header, grids));
}

async function loadCube(dir, name) {
    process.env.WIND_CUBE_DIR = dir;
    delete process.env.BLOB_READ_WRITE_TOKEN;
    return fetchWindCube({
        bounds: { latMin: 0, latMax: 1, lonMin: 0, lonMax: 1 }, levelHpa: 286.6,
        startMs: 0, endMs: HOUR, deviceId: name, kind: 'reconstruction',
    });
}

/* Three hourly slices along a "path": slice 1 is a wider box (v3 dims vary). All
 * boxes contain (12..14, 12..14); winds are uniform per slice so time blending
 * is checkable: u = 10, 20, 30 m/s. */
const TUBE_GRIDS = [box(10, 10, 5, 10, 0), box(8, 8, 9, 20, 0), box(12, 12, 5, 30, 0)];
const TUBE_HEADER = {
    v: 3, t0Ms: 0, stepMs: HOUR, gridStep: 1, levelHpa: 286.6, source: 'gfs',
    bounds: { latMin: 8, latMax: 16, lonMin: 8, lonMax: 16 },
    lat0: 10, dLat: 1, nLat: 5, lon0: 10, dLon: 1, nLon: 5, nGrids: 3,
    origins: [[10, 10], [8, 8], [12, 12]],
    dims: [[5, 5], [9, 9], [5, 5]],
};

test('v3 tube: per-slice dims decode and sample at the right offsets', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'stratolink-cube-'));
    try {
        writeCube(dir, 'dev', TUBE_HEADER, TUBE_GRIDS);
        const cube = await loadCube(dir, 'dev');
        assert.equal(cube.isTube, true);
        assert.equal(cube.levelHpa, 286.6);
        assert.deepEqual(cube.grids.map((g) => g.nLat), [5, 9, 5]);
        assert.deepEqual(cube.grids.map((g) => [g.lat0, g.lon0]), [[10, 10], [8, 8], [12, 12]]);
        /* A wrong per-grid point count would misalign every later slice. */
        assert.equal(sampleWind(cube, 12, 12, 0).u, 10);
        assert.equal(sampleWind(cube, 12, 12, HOUR).u, 20);
        assert.equal(sampleWind(cube, 12, 12, 2 * HOUR).u, 30);
        assert.equal(sampleWind(cube, 12, 12, HOUR / 2).u, 15);
        assert.deepEqual(bracketSlices(cube, 1.5 * HOUR), { h0: 1, h1: 2, f: 0.5 });
        assert.deepEqual(bracketSlices(cube, 9 * HOUR), { h0: 1, h1: 2, f: 1 });
    } finally {
        rmSync(dir, { recursive: true });
    }
});

test('cubeCovers: a tube point must be inside both bracketing slice boxes, not just the union', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'stratolink-cube-'));
    try {
        writeCube(dir, 'dev', TUBE_HEADER, TUBE_GRIDS);
        const cube = await loadCube(dir, 'dev');
        assert.equal(cubeCovers(cube, 12, 12, 0), true);
        /* Inside the union bounds (8..16) but outside slice 0's box (10..14). */
        assert.equal(cubeCovers(cube, 9, 9, 0), false);
        assert.equal(cubeCovers(cube, 15, 15, 0), false);
        /* Between slices 1 (8..16) and 2 (12..16): only their intersection counts. */
        assert.equal(cubeCovers(cube, 9, 9, 1.5 * HOUR), false);
        assert.equal(cubeCovers(cube, 13, 13, 1.5 * HOUR), true);
        assert.equal(cubeCovers(cube, 16, 16, 1.5 * HOUR), true);
        /* Longitude is wrapped into the box's range like windAt does. */
        assert.equal(cubeCovers(cube, 12, 12 - 360, 0), true);
    } finally {
        rmSync(dir, { recursive: true });
    }
});

test('v1 static box: cubeCovers falls back to the cube bounds', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'stratolink-cube-'));
    try {
        const header = {
            v: 1, t0Ms: 0, stepMs: HOUR, gridStep: 1, levelHpa: 300,
            bounds: { latMin: 10, latMax: 14, lonMin: 10, lonMax: 14 },
            lat0: 10, dLat: 1, nLat: 5, lon0: 10, dLon: 1, nLon: 5, nGrids: 2,
        };
        writeCube(dir, 'dev', header, [box(10, 10, 5, 5, 0), box(10, 10, 5, 5, 0)]);
        const cube = await loadCube(dir, 'dev');
        assert.equal(cube.isTube, false);
        assert.equal(cubeCovers(cube, 12, 12, 0), true);
        assert.equal(cubeCovers(cube, 14.5, 12, 0), false);
    } finally {
        rmSync(dir, { recursive: true });
    }
});

test('integrateBalloonPathT stops when the path leaves its slice box, even inside the union bounds', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'stratolink-cube-'));
    try {
        /* Uniform 20 m/s southward wind; slice 0 spans lat 10..14, the union 8..16.
         * Start just inside slice 0 and drift south: the integration must stop at
         * the slice edge (~10°), not carry on down to the union edge (8°) on
         * edge-clamped winds. */
        const grids = [box(10, 10, 5, 0, -20), box(8, 8, 9, 0, -20), box(10, 10, 5, 0, -20)];
        writeCube(dir, 'dev', TUBE_HEADER, grids);
        const cube = await loadCube(dir, 'dev');
        const still = { speedSigma: 0, dirSigma: 0, altSigma: 0, tauHours: 18 };
        const path = integrateBalloonPathT(10.5, 12, cube, { speedMult: 1, dirOffsetDeg: 0 }, still, 0, 3);
        assert.equal(path.length, 2, `path ${JSON.stringify(path)}`);
        assert.ok(path[1][1] < 10 && path[1][1] > 9.8, `exit point ${path[1]}`);
    } finally {
        rmSync(dir, { recursive: true });
    }
});
