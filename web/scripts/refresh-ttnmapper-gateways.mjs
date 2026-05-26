#!/usr/bin/env node
/**
 * Snapshot ttnmapper.org's public gateway list to a static JSON file in
 * `public/` so the dashboard can render the LoRaWAN coverage layer
 * without an API call on every page load.
 *
 * Run manually whenever you want fresh data:
 *
 *     npm run gateways:refresh
 *
 * Gateways move on the scale of weeks, so a monthly refresh is plenty.
 * Wire this into a cron / CI step if you want it automated.
 *
 * Outputs:
 *   public/ttnmapper-gateways.json — {gateways:[{lat,lon,net}], count, fetchedAt}
 *   public/ttnmapper-coverage.json — {coverage: MultiPolygon, fetchedAt}
 *                                    (union of 250 km buffers around every
 *                                    gateway — used to render a single
 *                                    coverage blob instead of 14k
 *                                    overlapping rings)
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buffer, union, featureCollection, point, simplify } from '@turf/turf';

const NETWORKS = [
    { id: 'NS_TTS_V3://ttn@000013', tag: 'v3' },
    { id: 'thethingsnetwork.org',    tag: 'v2' },
];
/* Drop gateways silent longer than this. Keeps the snapshot pruned. */
const RECENT_DAYS = 30;
/* Coverage radii around each gateway, km.
 * - 150 km: tight, conservative "definite reception" range.
 * - 250 km: looser, optimistic "best-case line-of-sight" range.
 * Both get a union polygon; the UI renders the inner filled and the
 * outer as an outline-only overlay so the operator sees both. */
const COVERAGE_KM_PRIMARY = 150;
const COVERAGE_KM_OUTER = 250;
/* Buffer resolution. 16 segments gives a smooth-enough circle for
 * dashboard rendering at any zoom and unions ~4× faster than 64. */
const BUFFER_STEPS = 16;
/* Spatial bucket size for the divide-and-conquer union. Smaller =
 * more buckets, each cheaper to union, but more boundary buckets need
 * to be merged in the second pass. 5° works well for our ~14k inputs. */
const BUCKET_DEG = 5;
/* Douglas–Peucker tolerance, in degrees, applied to the unioned coverage
 * polygons before they're written. 0.05° ≈ 5.5 km at the equator —
 * invisible at the country-scale zooms where coverage is read, and cuts
 * vertex count (and therefore JSON size and client-side tessellation
 * cost) by ~4×. Without this the unioned MultiPolygon ships ~20k vertices
 * and ~770 KB per file, which made tab switches feel sluggish in
 * dashboards that mount multiple maps. */
const SIMPLIFY_TOLERANCE_DEG = 0.05;

const here = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(here, '..', 'public', 'ttnmapper-gateways.json');
const coveragePath = resolve(here, '..', 'public', 'ttnmapper-coverage.json');
const coverageOuterPath = resolve(here, '..', 'public', 'ttnmapper-coverage-outer.json');

async function fetchNetwork(id, tag, cutoff) {
    const url = `https://api.ttnmapper.org/network/${encodeURIComponent(id)}/gateways`;
    const r = await fetch(url, {
        headers: {
            /* Their CDN blocks the default Node UA. */
            'User-Agent': 'Mozilla/5.0 (compatible; Stratolink-Snapshot/1.0)',
            'Accept': 'application/json',
            'Origin': 'https://ttnmapper.org',
            'Referer': 'https://ttnmapper.org/',
        },
    });
    if (!r.ok) throw new Error(`ttnmapper ${tag} returned ${r.status}`);
    const body = await r.json();
    return body
        .filter(g =>
            Number.isFinite(g.latitude)
            && Number.isFinite(g.longitude)
            && Math.abs(g.latitude) > 0.01
            && Math.abs(g.longitude) > 0.01
            && g.latitude >= -90 && g.latitude <= 90
            && g.longitude >= -180 && g.longitude <= 180
            && Date.parse(g.last_heard) >= cutoff
        )
        .map(g => ({
            /* ~10 m precision — well under what we render at any zoom. */
            lat: Math.round(g.latitude * 1e4) / 1e4,
            lon: Math.round(g.longitude * 1e4) / 1e4,
            net: tag,
        }));
}

/**
 * Compute the union of 250 km buffers around every gateway. With ~14k
 * gateways a naive pairwise union (`(((b1 ∪ b2) ∪ b3) ∪ …)`) takes
 * minutes and produces an enormous outline. We instead:
 *   1. Bucket gateways into BUCKET_DEG × BUCKET_DEG lat/lon cells.
 *   2. Union all buffers inside each cell (small, fast).
 *   3. Union the per-cell results into one global MultiPolygon.
 * Step 2 is `O(n_cell)` per cell and runs in parallel across cells.
 * Step 3 is `O(n_buckets)` — usually <100 cells.
 */
function computeCoverageUnion(gateways, coverageKm) {
    /* Pass 1 — bucket the points. */
    const cells = new Map(); /* key "lat_lon" → array of points */
    for (const g of gateways) {
        const ci = Math.floor(g.lat / BUCKET_DEG);
        const cj = Math.floor(g.lon / BUCKET_DEG);
        const key = `${ci}_${cj}`;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(g);
    }

    /* Pass 2 — buffer + union inside each cell. */
    const cellPolygons = [];
    let i = 0;
    for (const [key, pts] of cells) {
        const fc = featureCollection(pts.map(p => point([p.lon, p.lat])));
        let buffered;
        try {
            buffered = buffer(fc, coverageKm, { units: 'kilometers', steps: BUFFER_STEPS });
        } catch (e) {
            console.warn(`buffer failed for cell ${key}:`, e?.message ?? e);
            continue;
        }
        if (!buffered || !buffered.features?.length) continue;
        /* Union all polygons in this cell. */
        const merged = unionAll(buffered.features);
        if (merged) cellPolygons.push(merged);
        i++;
        if (i % 20 === 0) process.stdout.write(`  cells unioned: ${i}/${cells.size}\r`);
    }
    process.stdout.write(`  cells unioned: ${cells.size}/${cells.size}\n`);

    /* Pass 3 — union the per-cell polygons. They overlap across cell
     * boundaries (the buffer extends BUFFER_KM past the cell edge), so
     * we need a final merge. */
    console.log('  merging cell polygons…');
    return unionAll(cellPolygons);
}

/** Reduce-style union of N polygons via balanced binary tree to keep
 *  intermediate vertex counts manageable. */
function unionAll(polys) {
    if (polys.length === 0) return null;
    if (polys.length === 1) return polys[0];
    let level = polys.slice();
    while (level.length > 1) {
        const next = [];
        for (let i = 0; i < level.length; i += 2) {
            if (i + 1 >= level.length) {
                next.push(level[i]);
                continue;
            }
            const fc = featureCollection([level[i], level[i + 1]]);
            try {
                const u = union(fc);
                if (u) next.push(u);
            } catch (e) {
                /* Geometry weirdness on the union — keep both originals. */
                next.push(level[i]);
                next.push(level[i + 1]);
                console.warn('union step failed:', e?.message ?? e);
            }
        }
        level = next;
    }
    return level[0];
}

async function main() {
    const cutoff = Date.now() - RECENT_DAYS * 24 * 60 * 60 * 1000;
    console.log(`Fetching ttnmapper gateway lists (active in last ${RECENT_DAYS} days)…`);
    const buckets = await Promise.all(
        NETWORKS.map(({ id, tag }) => fetchNetwork(id, tag, cutoff)),
    );
    const gateways = buckets.flat();
    const fetchedAt = Date.now();
    const payload = { gateways, count: gateways.length, fetchedAt };

    await mkdir(dirname(outPath), { recursive: true });
    await writeFile(outPath, JSON.stringify(payload));
    const byNet = gateways.reduce((acc, g) => {
        acc[g.net] = (acc[g.net] ?? 0) + 1;
        return acc;
    }, {});
    console.log(`Wrote ${gateways.length} gateways → ${outPath}`);
    console.log('  by network:', byNet);

    /* Coverage unions — primary (definite reception) + outer (best-case
     * line-of-sight). Run sequentially: the buffer compute is CPU-bound
     * and doesn't parallelise on a single Node thread. */
    const fs = await import('node:fs/promises');
    for (const radiusKm of [COVERAGE_KM_PRIMARY, COVERAGE_KM_OUTER]) {
        console.log(`\nComputing ${radiusKm} km coverage union…`);
        const t0 = Date.now();
        const merged = computeCoverageUnion(gateways, radiusKm);
        if (!merged) {
            console.warn(`  ${radiusKm} km coverage union failed — skipping`);
            continue;
        }
        const isPrimary = radiusKm === COVERAGE_KM_PRIMARY;
        const path = isPrimary ? coveragePath : coverageOuterPath;
        const simplified = simplify(merged, {
            tolerance: SIMPLIFY_TOLERANCE_DEG,
            highQuality: false,
            mutate: true,
        });
        const payload = {
            coverage: simplified.geometry,
            radiusKm,
            bufferSteps: BUFFER_STEPS,
            simplifyTolerance: SIMPLIFY_TOLERANCE_DEG,
            fetchedAt,
        };
        await writeFile(path, JSON.stringify(payload));
        const stat = await fs.stat(path);
        console.log(`  Wrote ${radiusKm} km → ${path} (${(stat.size / 1024).toFixed(1)} KB, ${((Date.now() - t0) / 1000).toFixed(1)} s)`);
    }
}

main().catch((err) => {
    console.error('refresh-ttnmapper-gateways failed:', err);
    process.exit(1);
});
