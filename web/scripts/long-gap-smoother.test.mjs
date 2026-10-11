/**
 * Two-filter long-gap smoother (lib/wind/pathReconstructionLongGap.ts):
 *   - systematic resampling and the filter-level resample step
 *   - the join: overlap-window blend of a forward and a backward half
 *   - end to end on an in-memory uniform-wind cube: a straight, pinned,
 *     well-populated bridge, and the tube penalty keeping the posterior inside
 * No NOAA, no numpy, no network.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
    effectiveSampleSize, joinHalves, reconstructLongGap, resampleIfCollapsed, systematicResample, trimmedLocalMean,
} from '../lib/wind/pathReconstructionLongGap.ts';

const HOUR = 3_600_000;

test('systematicResample: equal weights reproduce every particle exactly once, in order', () => {
    for (const u0 of [0.01, 0.5, 0.99]) {
        assert.deepEqual([...systematicResample([1, 1, 1, 1, 1], 5, u0)], [0, 1, 2, 3, 4]);
    }
});

test('systematicResample: a single non-zero weight is the only ancestor', () => {
    assert.deepEqual([...systematicResample([0, 0, 1, 0], 8)], new Array(8).fill(2));
});

test('systematicResample: each particle gets ⌊w·n⌋ or ⌈w·n⌉ copies (low variance), sorted', () => {
    const w = [0.1, 0.3, 0.6];
    const n = 1000;
    for (const u0 of [0.01, 0.37, 0.5, 0.99]) {
        const idx = systematicResample(w, n, u0);
        const counts = [0, 0, 0];
        for (const i of idx) counts[i] += 1;
        for (let i = 0; i < w.length; i++) {
            assert.ok(Math.abs(counts[i] - w[i] * n) <= 1, `particle ${i}: ${counts[i]} copies for weight ${w[i]}`);
        }
        for (let k = 1; k < idx.length; k++) assert.ok(idx[k] >= idx[k - 1]);
    }
    /* Unnormalized weights and a different output size work the same way. */
    const idx = systematicResample([2, 6], 40, 0.25);
    assert.equal(idx.filter((i) => i === 1).length, 30);
});

test('systematicResample: zero total weight falls back to the identity instead of NaN indices', () => {
    assert.deepEqual([...systematicResample([0, 0, 0], 3)], [0, 1, 2]);
});

test('effectiveSampleSize: (Σw)²/Σw²', () => {
    assert.equal(effectiveSampleSize([1, 1, 1, 1]), 4);
    assert.equal(effectiveSampleSize([0, 5, 0]), 1);
    assert.equal(effectiveSampleSize([]), 0);
    assert.ok(Math.abs(effectiveSampleSize([0.5, 0.5, 1]) - 8 / 3) < 1e-12);
});

function particle(logW, lat = 0) {
    return { lat, lon: 0, speedMult: 1, altOffset: 0, offA: 0, offB: 0, logW, outside: 0, path: [{ lat, lon: 0, alt: 0 }] };
}

test('resampleIfCollapsed: healthy weights are left alone (same array, same objects)', () => {
    const ps = [particle(0), particle(-0.1), particle(-0.2), particle(0)];
    const stats = { total: 0, outside: 0, resamples: 0 };
    const out = resampleIfCollapsed(ps, stats);
    assert.equal(out, ps);
    assert.equal(stats.resamples, 0);
});

test('resampleIfCollapsed: a collapsed filter is rebuilt from its survivors with private paths and reset weights', () => {
    /* Two survivors (weight 1 each) and six lineages the tube penalty killed
     * (e⁻⁵⁰): n_eff ≈ 2 < 8/2 → resample. Each survivor should get 4 copies. */
    const ps = [particle(0, 1), particle(-50), particle(-50), particle(-50), particle(0, 2), particle(-50), particle(-50), particle(-50)];
    const stats = { total: 0, outside: 0, resamples: 0 };
    const out = resampleIfCollapsed(ps, stats);
    assert.equal(stats.resamples, 1);
    assert.equal(out.length, 8);
    const lats = out.map((p) => p.lat).sort();
    assert.deepEqual(lats, [1, 1, 1, 1, 2, 2, 2, 2]);
    for (const p of out) {
        assert.equal(p.logW, 0);
        assert.equal(p.outside, 0);
    }
    /* Copies must not share a path array, or the next step would be written
     * into every sibling at once. */
    const paths = new Set(out.map((p) => p.path));
    assert.equal(paths.size, 8);
    assert.notEqual(out[0].path, ps[0].path);
    assert.deepEqual(out[0].path, ps[0].path);
});

test('joinHalves: pinned at both fixes, untouched outside the window, a C¹ blend inside it', () => {
    /* Forward half along lat 0 (lon = step), backward half along lat 1 back
     * from B = (lon 20, lat 1): a 1° offset across the whole overlap. */
    const nSteps = 20;
    const m = 10;
    const k = 3;
    const fwd = Array.from({ length: m + k + 1 }, (_, s) => ({ lat: 0, lon: s, alt: 1 }));
    const bwd = Array.from({ length: nSteps - m + k + 1 }, (_, s) => ({ lat: 1, lon: nSteps - s, alt: 3 }));
    const path = joinHalves(fwd, bwd, m, nSteps, k);
    assert.equal(path.length, nSteps + 1);
    assert.deepEqual(path[0], fwd[0]);
    assert.deepEqual(path[nSteps], bwd[0]);
    for (let s = 0; s <= m - k; s++) assert.deepEqual(path[s], fwd[s]);
    for (let s = m + k; s <= nSteps; s++) assert.deepEqual(path[s], bwd[nSteps - s]);
    assert.deepEqual(path[m], { lat: 0.5, lon: 10, alt: 2 });
    /* Lon is a straight line throughout; lat climbs monotonically from 0 to 1
     * with a smoothstep: the biggest increment at the centre, the smallest at
     * the window edges (no kink entering or leaving the blend). */
    const dLat = [];
    for (let s = 1; s <= nSteps; s++) {
        assert.ok(Math.abs(path[s].lon - path[s - 1].lon - 1) < 1e-12);
        const d = path[s].lat - path[s - 1].lat;
        assert.ok(d >= -1e-12, `lat must not go back at step ${s}`);
        dLat.push(d);
    }
    const inWindow = dLat.slice(m - k, m + k);                      // the 2k increments inside the window
    const centre = Math.max(...inWindow);
    assert.ok(Math.abs(dLat[m - 1] - dLat[m]) < 1e-12 && Math.abs(centre - dLat[m]) < 1e-12, 'the steepest increments straddle m');
    assert.ok(inWindow[0] < centre / 2, `edge increment ${inWindow[0]} vs centre ${centre}`);
    assert.ok(inWindow[inWindow.length - 1] < centre / 2);
    assert.ok(Math.abs(inWindow.reduce((a, b) => a + b, 0) - 1) < 1e-12, 'the window carries the whole 1° offset');
});

/** A static 1° box (lat/lon `lat0..lat0+n-1`) with uniform winds in every
 *  hourly slice — the WindCube shape `sampleWind` / `cubeCovers` read. */
function uniformCube(u, v, hours, { lat0 = -10, lon0 = -10, n = 61, latMax = null } = {}) {
    const nLat = latMax == null ? n : Math.round(latMax - lat0) + 1;
    const grid = () => ({
        lat0, dLat: 1, nLat, lon0, dLon: 1, nLon: n,
        U: new Float32Array(nLat * n).fill(u), V: new Float32Array(nLat * n).fill(v),
    });
    return {
        t0Ms: 0, stepMs: HOUR, gridStep: 1, levelHpa: 300, isTube: false, source: 'test',
        bounds: { latMin: lat0, latMax: lat0 + nLat - 1, lonMin: lon0, lonMax: lon0 + n - 1 },
        grids: Array.from({ length: hours + 2 }, grid),
    };
}

function fixes(hours, u, lat = 10, lon = 10) {
    const A = { lat, lon, alt_m: 9500, time_utc: new Date(0).toISOString() };
    const dLon = (u * hours * 3600) / (111_320 * Math.cos((lat * Math.PI) / 180));
    const B = { lat, lon: lon + dLon, alt_m: 9500, time_utc: new Date(hours * HOUR).toISOString() };
    return { A, B };
}

/* A two-route bundle: 70 % of the sample paths follow route A (lat 0), 30 %
 * route B (lat 2°), all with small jitter. The posterior mean sits at 0.6°,
 * a latitude no sample ever had; the trimmed local mean must follow route A. */
function twoRoutes(seed = 1) {
    let x = seed;
    const rnd = () => { x = (x * 1664525 + 1013904223) % 4294967296; return x / 4294967296 - 0.5; };
    const samples = [];
    for (let i = 0; i < 200; i++) {
        const base = i < 140 ? 0 : 2;
        const off = rnd() * 0.1;
        const path = [];
        for (let s = 0; s <= 60; s++) path.push({ lat: base + off + rnd() * 0.02, lon: s * 0.1, alt: 9500 });
        samples.push(path);
    }
    return samples;
}

test('trimmedLocalMean: a two-route bundle gives a line on the dominant route, not between the routes', () => {
    const samples = twoRoutes();
    const { path, medoid, kept } = trimmedLocalMean(samples, 0.1, 100, 3);
    assert.equal(path.length, 61);
    assert.equal(kept, 20);
    assert.ok(medoid < 140, 'the medoid is a route-A sample');
    for (const p of path) assert.ok(Math.abs(p.lat) < 0.1, `line latitude ${p.lat} should sit on route A`);
    /* For contrast, the plain mean of the same samples sits in the void. */
    const meanLat = samples.reduce((a, sm) => a + sm[30].lat, 0) / samples.length;
    assert.ok(meanLat > 0.5 && meanLat < 0.7, `mean latitude ${meanLat} is between the routes`);
});

test('trimmedLocalMean: identical samples reproduce the path; the trim never keeps fewer than three', () => {
    const path = Array.from({ length: 10 }, (_, s) => ({ lat: 40 + s * 0.01, lon: -120 + s * 0.2, alt: 9000 }));
    const samples = Array.from({ length: 12 }, () => path.map((p) => ({ ...p })));
    const out = trimmedLocalMean(samples, 0.1, 5, 2);
    assert.equal(out.kept, 3);
    out.path.forEach((p, s) => { assert.ok(Math.abs(p.lat - path[s].lat) < 1e-9 && Math.abs(p.lon - path[s].lon) < 1e-9); });
});

test('reconstructLongGap: a uniform wind that carries A exactly to B gives a straight, pinned, well-populated bridge', async () => {
    const u = 20;
    const { A, B } = fixes(6, u);
    const r = await reconstructLongGap(A, B, [], uniformCube(u, 0, 6));
    assert.equal(r.short, false);
    assert.equal(r.meanPath.length, 19);                            // 6 h / 20 min + 1
    assert.deepEqual(r.meanPath[0], [10, 10]);                      // starts at A …
    assert.ok(Math.abs(r.meanPath[18][0] - B.lon) < 1e-3 && Math.abs(r.meanPath[18][1] - 10) < 1e-3); // … ends at B
    for (const [, lat] of r.meanPath) assert.ok(Math.abs(lat - 10) < 0.1, `lat ${lat}`);
    for (let s = 1; s < r.meanPath.length; s++) assert.ok(r.meanPath[s][0] > r.meanPath[s - 1][0], 'lon must advance every step');
    assert.ok(r.n_eff >= 40, `n_eff ${r.n_eff}`);
    assert.ok(r.endpoint_miss_km < 15, `closure ${r.endpoint_miss_km} km`);
    assert.ok(r.mid_gap_90_km < 120, `mid-gap 90% ${r.mid_gap_90_km} km`);
    assert.equal(r.mode, 'line');
    assert.equal(r.outside_cube_frac, 0);
    assert.equal(r.outside_cube_frac_weighted, 0);
    assert.equal(r.occupancy, null);
    assert.deepEqual(r.ellipses.map((e) => e.frac), [0.15, 0.3, 0.5, 0.7, 0.85]);
    for (const e of r.ellipses) assert.ok(e.e50.semi_a_km <= e.e90.semi_a_km && e.e90.polygon.length === 49);
    assert.ok(r.directness >= 0.99, `directness ${r.directness}`);
    assert.equal(r.dt_hours, 6);
});

test('reconstructLongGap: a tube one degree tall — lineages that leave it are penalized out of the posterior', async () => {
    /* Same kind of transit, but the cube's box only spans lat 9.5..10.5
     * (±55 km). Heading-perturbed lineages stray out in numbers (raw outside
     * fraction well above zero) and the 12 h gap crosses a heading-walk knot,
     * so the filters resample; the bridge must still be drawn from lineages
     * that stayed in: posterior-weighted outside fraction ≈ 0 and every
     * mean-path vertex inside the box. */
    const u = 12;
    const { A, B } = fixes(12, u);
    const cube = uniformCube(u, 0, 12, { lat0: 9.5, latMax: 10.5 });
    const r = await reconstructLongGap(A, B, [], cube);
    assert.ok(r.outside_cube_frac > 0.02, `raw outside ${r.outside_cube_frac}`);
    assert.ok(r.outside_cube_frac_weighted < 0.01, `weighted outside ${r.outside_cube_frac_weighted}`);
    for (const [, lat] of r.meanPath) assert.ok(lat >= 9.5 && lat <= 10.5, `mean path lat ${lat} outside the box`);
    assert.ok(Math.abs(r.meanPath[r.meanPath.length - 1][0] - B.lon) < 1e-3);
    assert.ok(r.n_eff >= 40, `n_eff ${r.n_eff}`);
});

test('reconstructLongGap: gaps under 30 min are a straight line with no particles', async () => {
    const A = { lat: 10, lon: 10, alt_m: 9500, time_utc: new Date(0).toISOString() };
    const B = { lat: 10.1, lon: 10.2, alt_m: 9500, time_utc: new Date(20 * 60_000).toISOString() };
    const r = await reconstructLongGap(A, B, [], uniformCube(0, 0, 1));
    assert.equal(r.short, true);
    assert.deepEqual(r.meanPath, [[10, 10], [10.1, 10.05], [10.2, 10.1]]);
    assert.equal(r.mode, 'line');
});
