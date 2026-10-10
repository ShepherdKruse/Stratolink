import { get, list } from '@vercel/blob';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import type { WindGridBounds } from './fetchWindGrid';
import { isBlobStorageConfigured } from './forecastStorage';
import { windAt, type GfsGrid } from './gfsGrid';

/**
 * A shared space-time wind field for one forecast compute: a stack of hourly (or
 * 3-hourly) NOAA grids built by scripts/gfs_ingest.py and read back from disk.
 * Every trajectory — the predicted-hindcast dead-reckon (fix → now), the forward
 * forecast (now → horizon), and every ensemble member — samples this one field,
 * so they all see the same evolving winds and the two regimes stay continuous
 * (no source switch at "now").
 */
export type WindCube = {
    /** Epoch ms of grid hour 0 (floored to the hour). grids[h] = winds at t0Ms + h*stepMs. */
    t0Ms: number;
    stepMs: number;
    grids: GfsGrid[];
    bounds: WindGridBounds;
    gridStep: number;
    levelHpa: number;
    /** Where the field came from, as written by the ingest (e.g. 'gfs', 'gefs'). */
    source?: string;
    /** ISO time the cube was built (GFS ingest run), for staleness reporting. */
    generatedAt?: string;
    /** True for a v2 "tube" cube — each grid follows the trajectory, so the
     *  box-center sequence IS the pre-integrated nominal path (see `centerTrack`). */
    isTube?: boolean;
    /** Tube cubes only: the TRUE per-slice trajectory centers, `[lat, lon]` with
     *  lon UNWRAPPED (like `origins`). The box origins are snapped to the source
     *  grid for exact sampling, so box centers quantize the path to 0.25-0.5°;
     *  these carry the unsnapped positions. Absent on cubes built before this. */
    centers?: Array<[number, number]>;
    /** Tube cubes only: the same pre-integrated walk sampled every `stepMs`
     *  (hourly), `points` = `[lat, lon]` unwrapped — denser than the 3-6 h slice
     *  cadence, so hourly member paths need no chord interpolation. */
    track?: { t0Ms: number; stepMs: number; points: Array<[number, number]> };
};

/** The pre-integrated trajectory a tube was laid along: each slice's box center
 *  (origin + half-extent). For a member cube this is that member's full path
 *  through its own flow — exact, so the compute reads it instead of re-integrating
 *  through the 3-hourly boxes (which drifts/clamps for fast members over a long
 *  gap). Longitudes stay unwrapped (continuous across ±180). */
export function centerTrack(cube: WindCube): Array<[number, number]> {
    /* Prefer the TRUE centers stored at ingest (header is [lat, lon]; swap to this
     * function's [lon, lat]). The box-center fallback below is quantized to the
     * source lattice (box origins are grid-snapped for exact sampling), which drew
     * straight chords and right-angle staircases — kept only for old cubes. */
    if (cube.centers && cube.centers.length === cube.grids.length) {
        return cube.centers.map(([lat, lon]) => [lon, lat] as [number, number]);
    }
    return cube.grids.map((g) => [
        g.lon0 + ((g.nLon - 1) * g.dLon) / 2,
        g.lat0 + ((g.nLat - 1) * g.dLat) / 2,
    ] as [number, number]);
}

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
    /** v2 tube (optional): TRUE per-slice centers `[lat, lon]`, lon unwrapped. */
    centers?: Array<[number, number]>;
    /** v2 tube (optional): hourly true trajectory, `points` = `[lat, lon]`. */
    track?: { t0Ms: number; stepMs: number; points: Array<[number, number]> };
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
        isTube: !!h.origins,
        centers: h.centers, track: h.track,
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

/** Read a device's cube from the Blob `cubes/` prefix, or null if none exists.
 *  Legacy path: the retired upload step wrote these; nothing uploads cubes any
 *  more, so in practice this only serves a hand-run scripts/upload_cubes.mjs.
 *  Tries `.slwc.gz`, `.slwc`, `.json.gz`, `.json`; the `forecast` kind falls back
 *  to the full cube if no `-fc` cube exists. Never throws. */
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
 * Read a device's pre-ingested cube: the hourly `forecast` tube or the
 * full-mission `reconstruction` cube (see scripts/gfs_ingest.py). Precedence:
 *   1. WIND_CUBE_DIR — per-device cubes on local disk (the GitHub Actions worker
 *      compute: build cubes on the runner, read them here, no Blob round-trip).
 *   2. Blob `cubes/{device}…` — legacy serverless read path (nothing writes it).
 * There is deliberately NO live weather fallback: Open-Meteo must never be on the
 * production path, so a device without a cube fails loudly here instead.
 */
export async function fetchWindCube(opts: {
    /** Device whose pre-ingested cube to read. */
    deviceId: string;
    /** Which pre-ingested cube to read (default 'reconstruction'). */
    kind?: CubeKind;
}): Promise<WindCube> {
    const kind: CubeKind = opts.kind ?? 'reconstruction';
    const cubeDir = process.env.WIND_CUBE_DIR;
    if (cubeDir) {
        const cube = await readCubeFromDir(cubeDir, opts.deviceId, kind);
        if (cube) return cube;
    }
    const cube = await readCubeFromBlob(opts.deviceId, kind);
    if (cube) return cube;
    const looked = [
        cubeDir ? `WIND_CUBE_DIR=${cubeDir}` : 'WIND_CUBE_DIR (unset)',
        isBlobStorageConfigured() ? 'Blob cubes/' : 'Blob (not configured)',
    ].join(', ');
    throw new Error(
        `No ${kind} wind cube for device "${opts.deviceId}" (looked in ${looked}). ` +
        'Run scripts/gfs_ingest.py to build it; there is no live weather fallback.',
    );
}
