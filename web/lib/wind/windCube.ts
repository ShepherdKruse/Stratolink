import { get, list } from '@vercel/blob';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import { fetchWindGridHourlySeries, snapPressureHpa, type WindGridBounds } from './fetchWindGrid';
import { isBlobStorageConfigured } from './forecastStorage';
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
    /** Where the field came from: 'gfs' (pre-ingested) or 'open-meteo' (live fallback). */
    source?: string;
    /** ISO time the cube was built (GFS ingest run), for staleness reporting. */
    generatedAt?: string;
};

/** JSON shape of a pre-ingested cube (local file or Blob). */
type RawCube = {
    t0Ms: number;
    stepMs: number;
    gridStep: number;
    levelHpa: number;
    bounds: WindGridBounds;
    grids: Array<{ lat0: number; dLat: number; nLat: number; lon0: number; dLon: number; nLon: number; U: number[]; V: number[] }>;
    source?: string;
    generated_at?: string;
};

const HOUR_MS = 3_600_000;

/** Reconstitute a WindCube from its JSON form (Float32Array U/V). */
function cubeFromRaw(raw: RawCube): WindCube {
    return {
        t0Ms: raw.t0Ms,
        stepMs: raw.stepMs,
        gridStep: raw.gridStep,
        levelHpa: raw.levelHpa,
        bounds: raw.bounds,
        source: raw.source ?? 'gfs',
        generatedAt: raw.generated_at,
        grids: raw.grids.map((g) => ({
            lat0: g.lat0, dLat: g.dLat, nLat: g.nLat, lon0: g.lon0, dLon: g.dLon, nLon: g.nLon,
            U: new Float32Array(g.U), V: new Float32Array(g.V),
        })),
    };
}

/** Header of the packed binary cube (`.slwc`).
 *  v1: geometry is constant across grids, so it lives here once (`lat0`/`lon0`).
 *  v2 ("tube"): cell size + dims are shared (`dLat`/`nLat`/`dLon`/`nLon`), but each
 *  time-slice follows the trajectory, so its origin lives in `origins[g]` =
 *  `[lat0, lon0]`. `bounds` is the union of every slice's box. The int16 payload
 *  layout is identical in both versions. */
type BinHeader = {
    v: number; scale: number;
    t0Ms: number; stepMs: number; gridStep: number; levelHpa: number;
    bounds: WindGridBounds; source?: string; generated_at?: string;
    lat0: number; dLat: number; nLat: number; lon0: number; dLon: number; nLon: number;
    nGrids: number;
    /** v2 tube: per-slice `[lat0, lon0]`, length `nGrids` (dims/step stay shared). */
    origins?: Array<[number, number]>;
};

/** Reconstitute a WindCube from the packed binary form:
 *    [uint32 LE headerLen][header JSON utf-8, padded to 4-byte boundary]
 *    [ per grid: int16 U[nLat*nLon] then int16 V[nLat*nLon], little-endian ]
 *  Values are stored as int16 = round(value*scale) — lossless vs the old 0.1 m/s
 *  JSON rounding — and decoded to Float32 (÷scale) so `windAt` and every caller
 *  stay byte-for-byte unchanged. ~zero parse cost vs JSON.parse of millions of
 *  numbers; this is what makes the GEFS 31× member volume tractable. */
function cubeFromBinary(raw: Buffer): WindCube {
    /* Copy to a fresh ArrayBuffer at offset 0 — a gunzip/Blob Buffer can sit at a
     * non-2-aligned byteOffset in a pool, which Int16Array views forbid. */
    const ab = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
    const dv = new DataView(ab);
    const headerLen = dv.getUint32(0, true);
    const h = JSON.parse(Buffer.from(ab, 4, headerLen).toString('utf8')) as BinHeader;
    const scale = h.scale || 10;
    const n = h.nLat * h.nLon;
    let off = 4 + headerLen; /* 4-byte aligned by the writer's padding */
    const grids: GfsGrid[] = [];
    for (let g = 0; g < h.nGrids; g++) {
        const U16 = new Int16Array(ab, off, n); off += n * 2;
        const V16 = new Int16Array(ab, off, n); off += n * 2;
        /* v2 tube: each slice has its own origin (it follows the path); v1: shared. */
        const lat0 = h.origins ? h.origins[g][0] : h.lat0;
        const lon0 = h.origins ? h.origins[g][1] : h.lon0;
        grids.push({
            lat0, dLat: h.dLat, nLat: h.nLat, lon0, dLon: h.dLon, nLon: h.nLon,
            U: Float32Array.from(U16, (x) => x / scale),
            V: Float32Array.from(V16, (x) => x / scale),
        });
    }
    return {
        t0Ms: h.t0Ms, stepMs: h.stepMs, gridStep: h.gridStep, levelHpa: h.levelHpa,
        bounds: h.bounds, source: h.source ?? 'gfs', generatedAt: h.generated_at, grids,
    };
}

/** Decode a cube blob by filename: gunzip `.gz`, then binary `.slwc` or JSON. */
function decodeCube(name: string, buf: Buffer): WindCube {
    const gz = name.endsWith('.gz');
    const body = gz ? gunzipSync(buf) : buf;
    const base = gz ? name.slice(0, -3) : name;
    return base.endsWith('.slwc')
        ? cubeFromBinary(body)
        : cubeFromRaw(JSON.parse(body.toString('utf8')) as RawCube);
}

/** Which cube to read for a device — the small hourly forecast cube or the
 *  full-mission reconstruction cube (see scripts/gfs_ingest.py). */
export type CubeKind = 'forecast' | 'reconstruction';

/** Read+decode one Blob cube object by key (gunzips `.json.gz`, plain-reads
 *  `.json`), or null if absent/unreadable. Never throws. */
async function getCubeObject(key: string): Promise<WindCube | null> {
    try {
        const r = await get(key, { access: 'private', useCache: false });
        if (!r || r.statusCode !== 200) return null;
        return decodeCube(key, Buffer.from(await new Response(r.stream).arrayBuffer()));
    } catch {
        return null;
    }
}

/** Read a device's pre-ingested cube from Blob, or null if none exists yet.
 *  The `forecast` cube (`cubes/{id}-fc.json.gz`) is small + hourly; the
 *  `reconstruction` cube (`cubes/{id}.json.gz`) is the full mission. Prefers the
 *  gzipped object, falls back to the legacy uncompressed one (deploy window), and
 *  the forecast read falls back to the full cube if no `-fc` cube exists yet
 *  (so the app is safe to deploy before the two-cube ingest first runs). Never throws. */
/** Read a device's cube from a LOCAL directory (same filenames as Blob). Used by
 *  the GitHub Actions worker compute, which builds cubes on the runner and reads
 *  them straight off disk — no Blob round-trip — so big multi-member ensembles
 *  never have to be pulled into the memory/time-limited serverless function. Set
 *  `WIND_CUBE_DIR` to enable. Never throws. */
async function readCubeFromDir(dir: string, deviceId: string, kind: CubeKind): Promise<WindCube | null> {
    for (const name of cubeCandidates(encodeURIComponent(deviceId), kind)) {
        try {
            return decodeCube(name, await readFile(join(dir, name)));
        } catch { /* try next candidate */ }
    }
    return null;
}

/** Filenames to try for a device's cube, newest format first: binary `.slwc`
 *  (gzipped then raw) before legacy JSON, so old cubes still read during the
 *  format-migration deploy window. The `forecast` kind also falls back to the
 *  full reconstruction cube if no `-fc` cube exists yet. */
function cubeCandidates(id: string, kind: CubeKind): string[] {
    const variants = (stem: string) => [`${stem}.slwc.gz`, `${stem}.slwc`, `${stem}.json.gz`, `${stem}.json`];
    return kind === 'forecast' ? [...variants(`${id}-fc`), ...variants(id)] : variants(id);
}

async function readCubeFromBlob(deviceId: string, kind: CubeKind): Promise<WindCube | null> {
    if (!isBlobStorageConfigured()) return null;
    for (const name of cubeCandidates(encodeURIComponent(deviceId), kind)) {
        const cube = await getCubeObject(`cubes/${name}`);
        if (cube) return cube;
    }
    return null;
}

/* ── GEFS ensemble: per-member cubes ({device}-mNN.slwc) ───────────────────────
 * The ensemble compute integrates one trajectory per member (each in its own
 * flow). Members are listed and loaded one at a time so peak memory stays flat
 * regardless of member count — the .slwc binary makes a single member's load
 * cheap. Empty list ⇒ no GEFS ensemble for this device (fall back to the
 * parametric jitter). */
export async function listMemberCubes(deviceId: string): Promise<string[]> {
    const id = encodeURIComponent(deviceId);
    /* `-mNN` = physics GEFS members, `-aNN` = AIGEFS (AI) members. Both are pooled
     * into one multi-model ensemble. */
    const re = new RegExp(`^${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}-([ma]\\d+)\\.slwc(\\.gz)?$`);
    const dir = process.env.WIND_CUBE_DIR;
    if (dir) {
        try {
            const labels = new Set<string>();
            for (const f of await readdir(dir)) {
                const m = f.match(re);
                if (m) labels.add(m[1]);
            }
            return [...labels].sort();
        } catch { return []; }
    }
    if (isBlobStorageConfigured()) {
        try {
            const { blobs } = await list({ prefix: `cubes/${id}-` });
            const labels = new Set<string>();
            for (const b of blobs) {
                const m = b.pathname.replace(/^cubes\//, '').match(re);
                if (m) labels.add(m[1]);
            }
            return [...labels].sort();
        } catch { return []; }
    }
    return [];
}

/** Load one member's cube ({device}-mNN), local-dir first then Blob. */
export function fetchMemberCube(deviceId: string, member: string): Promise<WindCube | null> {
    const dir = process.env.WIND_CUBE_DIR;
    const id = `${deviceId}-${member}`;
    return dir ? readCubeFromDir(dir, id, 'reconstruction') : readCubeFromBlob(id, 'reconstruction');
}

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
    /** Device whose pre-ingested cube to serve from Blob. */
    deviceId?: string;
    /** Which pre-ingested cube to serve (default 'reconstruction'). */
    kind?: CubeKind;
}): Promise<WindCube> {
    /* Source precedence:
     *   1. WIND_CUBE_FILE / WIND_CUBE_FC_FILE — single local file overrides (dev / spike).
     *   2. WIND_CUBE_DIR — per-device cubes on local disk (the GitHub Actions worker
     *      compute: build cubes on the runner, read them here, no Blob round-trip).
     *   3. Blob cube for the device — the pre-ingested cube (scripts/gfs_ingest.py),
     *      the serverless read path: no live wind API, no rate limit.
     *   4. Open-Meteo — live fallback for devices with no cube yet (migration safety;
     *      the call budget protects it). */
    const kind: CubeKind = opts.kind ?? 'reconstruction';
    const fcFile = process.env.WIND_CUBE_FC_FILE;
    const localFile = process.env.WIND_CUBE_FILE;
    if (kind === 'forecast' && fcFile) {
        return cubeFromRaw(JSON.parse(await readFile(fcFile, 'utf8')) as RawCube);
    }
    if (localFile) {
        return cubeFromRaw(JSON.parse(await readFile(localFile, 'utf8')) as RawCube);
    }
    /* Worker compute: read the just-built cubes from the runner's disk by device,
     * before any Blob read (this is the "compute where the data is" path). */
    const cubeDir = process.env.WIND_CUBE_DIR;
    if (cubeDir && opts.deviceId) {
        const cube = await readCubeFromDir(cubeDir, opts.deviceId, kind);
        if (cube) return cube;
    }
    if (opts.deviceId) {
        const cube = await readCubeFromBlob(opts.deviceId, kind);
        if (cube) return cube;
    }

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
    return {
        t0Ms, stepMs: HOUR_MS, grids, bounds: opts.bounds, gridStep, levelHpa,
        source: 'open-meteo', generatedAt: new Date().toISOString(),
    };
}
