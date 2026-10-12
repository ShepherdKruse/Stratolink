/**
 * Two-filter long-gap smoother (lib/wind/pathReconstructionLongGap.ts):
 *   - systematic resampling and the filter-level resample step
 *   - the join: overlap-window blend of a forward and a backward half
 *   - the AR(1) perturbation: stationary amplitude and exp(−lag/τ) memory
 *   - end to end on an in-memory uniform-wind cube: a straight, pinned,
 *     well-populated bridge, the tube penalty keeping the posterior inside,
 *     a gap the winds cannot connect reported as unexplained, and on a
 *     two-level cube particles that ride the wind at their own pressure
 * No NOAA, no numpy, no network.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import {
    ar1Step, chooseLine, effectiveSampleSize, joinHalves, reconstructLongGap, resampleIfCollapsed, systematicResample, trimmedLocalMean,
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
    return { lat, lon: 0, speedPert: 0, dirOff: 0, pOff: 0, altOffset: 0, logW, outside: 0, path: [{ lat, lon: 0, alt: 0 }] };
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

/** Deterministic standard normals (LCG + Box–Muller) so the statistics below are reproducible. */
function normals(seed) {
    let x = seed >>> 0;
    const u = () => { x = (Math.imul(x, 1664525) + 1013904223) >>> 0; return (x + 0.5) / 4294967296; };
    return () => Math.sqrt(-2 * Math.log(u())) * Math.cos(2 * Math.PI * u());
}

test('ar1Step: seeded from N(0, σ²) the process stays N(0, σ²) and forgets as exp(−lag/τ)', () => {
    const sigma = 12;
    const tau = 18;
    const dt = 1 / 3;                                               // 20-min steps
    const chains = 4000;
    const steps = 216;                                              // 72 h
    const g = normals(7);
    const x0 = Float64Array.from({ length: chains }, () => sigma * g());
    const x = Float64Array.from(x0);
    const lagCorr = (lagSteps) => {
        /* Pearson correlation between x at step 0 and at `lagSteps`, across chains. */
        let sxy = 0; let sxx = 0; let syy = 0;
        for (let c = 0; c < chains; c++) { sxy += x0[c] * x[c]; sxx += x0[c] * x0[c]; syy += x[c] * x[c]; }
        return sxy / Math.sqrt(sxx * syy);
    };
    let maxAbs = 0;
    for (let s = 1; s <= steps; s++) {
        for (let c = 0; c < chains; c++) {
            x[c] = ar1Step(x[c], sigma, dt, tau, g());
            if (Math.abs(x[c]) > maxAbs) maxAbs = Math.abs(x[c]);
        }
        if (s === 54 || s === 216) {                                // 18 h = τ, 72 h = 4τ
            let ss = 0;
            for (let c = 0; c < chains; c++) ss += x[c] * x[c];
            const sd = Math.sqrt(ss / chains);
            assert.ok(Math.abs(sd - sigma) < 0.05 * sigma, `stationary σ at step ${s}: ${sd}`);
            const want = Math.exp(-(s * dt) / tau);
            assert.ok(Math.abs(lagCorr(s) - want) < 0.04, `lag ${s * dt} h: corr ${lagCorr(s)} vs ${want}`);
        }
    }
    /* Bounded: no excursion beyond ~5σ in 864k draws (an unbounded walk would reach √216 × its step). */
    assert.ok(maxAbs < 5.5 * sigma, `max |x| ${maxAbs}`);
    /* Zero innovations decay geometrically toward zero; τ → ∞ holds the value. */
    assert.ok(Math.abs(ar1Step(10, sigma, tau, tau, 0) - 10 / Math.E) < 1e-12);
    assert.equal(ar1Step(10, sigma, 1, Infinity, 3), 10);
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

/** The same box with two pressure levels (250 / 300 hPa) of uniform eastward
 *  wind, shaped like a decoded v4 cube: `levelGrids` per slice plus the float
 *  level (`levelHpa`) in `grids`. */
function twoLevelCube(u250, u300, hours, levelHpa = 280) {
    const base = uniformCube(0, 0, hours);
    const grid = (u) => ({ ...base.grids[0], U: new Float32Array(base.grids[0].U.length).fill(u), V: new Float32Array(base.grids[0].U.length) });
    const w = (levelHpa - 250) / 50;
    return {
        ...base, levelHpa, levels: [250, 300],
        levelGrids: base.grids.map(() => [grid(u250), grid(u300)]),
        grids: base.grids.map(() => grid(u250 * (1 - w) + u300 * w)),
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

test('chooseLine: a split bundle gets the trimmed local mean, a single bundle the plain mean', () => {
    /* 70/30 two-route bundle (routes 2° = 222 km apart): the mean sits 67 km
     * off route A, outside a 40 km radius, so the split test must pick the
     * trimmed local mean on route A. */
    const split = chooseLine(twoRoutes(), 0.5, 40, 3);
    assert.equal(split.method, 'trimmed-local-mean');
    assert.ok(split.ratio < 0.5, `split ratio ${split.ratio}`);
    for (const p of split.path) assert.ok(Math.abs(p.lat) < 0.1, `line latitude ${p.lat} should sit on route A`);
    /* One route with the same jitter: the mean is inside the bundle, so it is
     * drawn, and it is exactly the per-step average of every draw. */
    const one = twoRoutes().slice(0, 140);
    const r = chooseLine(one, 0.5, 40, 3);
    assert.equal(r.method, 'posterior-mean');
    assert.equal(r.kept, 140);
    assert.ok(r.ratio > 0.8, `ratio ${r.ratio}`);
    const avg = one.reduce((a, sm) => a + sm[30].lat, 0) / one.length;
    assert.ok(Math.abs(r.path[30].lat - avg) < 1e-12);
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
    assert.equal(r.line_method, 'posterior-mean');
    assert.equal(r.occupancy, null);
    assert.deepEqual(r.ellipses.map((e) => e.frac), [0.15, 0.3, 0.5, 0.7, 0.85]);
    for (const e of r.ellipses) assert.ok(e.e50.semi_a_km <= e.e90.semi_a_km && e.e90.polygon.length === 49);
    assert.ok(r.directness >= 0.99, `directness ${r.directness}`);
    assert.equal(r.dt_hours, 6);
});

test('reconstructLongGap: a tube one degree tall — lineages that leave it are penalized out of the posterior', async () => {
    /* Same kind of transit, but the cube's box only spans lat 9.5..10.5
     * (±55 km). Heading-perturbed lineages stray out in numbers (raw outside
     * fraction well above zero) and the 12 h gap crosses resampling checks,
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

test('reconstructLongGap: a fix the winds cannot reach is reported unexplained, not bridged by cross-wind loops', async () => {
    /* A due-east 20 m/s wind for 12 h carries A 864 km east; B is that far east
     * but 2,000 km NORTH. Following the wind with a bounded heading offset, the
     * forward cloud stays near lat 10 and the backward cloud near lat 28, so
     * the two never come within reach: the gap must be flagged, low-confidence
     * corridor, with the closure reporting the miss. */
    const u = 20;
    const { A, B } = fixes(12, u);
    B.lat += 2000 / 111.32;
    const r = await reconstructLongGap(A, B, [], uniformCube(u, 0, 12));
    assert.equal(r.unexplained, true);
    assert.equal(r.mode, 'corridor');
    assert.equal(r.confidence, 'low');
    assert.ok(r.endpoint_miss_km > 1000, `closure ${r.endpoint_miss_km} km`);
    /* The well-posed transit is not flagged. */
    const ok = fixes(12, u);
    const r2 = await reconstructLongGap(ok.A, ok.B, [], uniformCube(u, 0, 12));
    assert.equal(r2.unexplained, false);
});

test('reconstructLongGap: on a multi-level cube particles read the wind at their own pressure, anchored at the fixes', async () => {
    /* 250 hPa blows 20 m/s east, 300 hPa 5 m/s. Over 24 h at 250 hPa the
     * balloon covers 1,728 km. Fixes that report 250 hPa are bridged cleanly;
     * the same two positions reported at 300 hPa cannot be: an 8 hPa pressure
     * wander never reaches the fast level, so the two clouds end ~1,300 km
     * apart at the midpoint. (A single-level read of the 280 hPa blend, 11 m/s,
     * would explain neither.) */
    const cube = twoLevelCube(20, 5, 24);
    const fast = fixes(24, 20);
    fast.A.pressure_hpa = 250;
    fast.B.pressure_hpa = 250;
    const r = await reconstructLongGap(fast.A, fast.B, [], cube);
    assert.equal(r.unexplained, false);
    assert.ok(r.endpoint_miss_km < 30, `closure ${r.endpoint_miss_km} km`);
    for (let s = 1; s < r.meanPath.length; s++) assert.ok(r.meanPath[s][0] > r.meanPath[s - 1][0]);
    const slow = fixes(24, 20);
    slow.A.pressure_hpa = 300;
    slow.B.pressure_hpa = 300;
    const r2 = await reconstructLongGap(slow.A, slow.B, [], cube);
    assert.equal(r2.unexplained, true);
    assert.equal(r2.mode, 'corridor');
});

test('reconstructLongGap: gaps under 30 min are a straight line with no particles', async () => {
    const A = { lat: 10, lon: 10, alt_m: 9500, time_utc: new Date(0).toISOString() };
    const B = { lat: 10.1, lon: 10.2, alt_m: 9500, time_utc: new Date(20 * 60_000).toISOString() };
    const r = await reconstructLongGap(A, B, [], uniformCube(0, 0, 1));
    assert.equal(r.short, true);
    assert.deepEqual(r.meanPath, [[10, 10], [10.1, 10.05], [10.2, 10.1]]);
    assert.equal(r.mode, 'line');
});
