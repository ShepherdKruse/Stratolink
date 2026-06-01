import { get, put } from '@vercel/blob';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { isBlobStorageConfigured } from './forecastStorage';
import type { ForecastGpsFix } from './forecastTypes';
import type { PathReconstructionResult } from './pathReconstruction';

/**
 * Content-addressed cache for the STATIC hindcast — the wind-reconstructed path
 * between known GPS fixes (`pathReconstruction`). It's a deterministic function
 * of the fixes + the (historical/analysis) winds at the fix-span midpoint, so
 * it shouldn't change once computed. We key it by a hash of those inputs and
 * reuse it across forecast recomputes, so the forward forecast can refresh on
 * its cadence without re-running (and visibly re-jittering) the hindcast.
 *
 * Mirrors `forecastStorage.ts`: Vercel Blob in prod, a gitignored local cache
 * in dev. Bumping ALGO_VERSION invalidates every cached hindcast.
 */
const ALGO_VERSION = 'v1';

export type StoredHindcast = PathReconstructionResult & { computed_at: string };

/** Stable 16-char hash of the inputs that fully determine the reconstruction:
 *  the GPS fixes (rounded to kill float jitter) + the pressure level + algo. */
export function hindcastInputHash(fixes: ForecastGpsFix[], levelHpa: number): string {
    const canon = fixes.map((f) => [
        Math.round(f.lat * 1e5),
        Math.round(f.lon * 1e5),
        new Date(f.time_utc).getTime(),
        f.alt_m != null && Number.isFinite(f.alt_m) ? Math.round(f.alt_m) : null,
    ]);
    const payload = JSON.stringify({ v: ALGO_VERSION, level: Math.round(levelHpa), fixes: canon });
    return createHash('sha256').update(payload).digest('hex').slice(0, 16);
}

function blobPath(deviceId: string, hash: string): string {
    return `hindcasts/${encodeURIComponent(deviceId)}-${hash}.json`;
}

const LOCAL_CACHE_DIR = join(process.cwd(), '.forecast-cache');

function localPath(deviceId: string, hash: string): string {
    const safe = deviceId.replace(/[^a-zA-Z0-9._-]/g, '_');
    return join(LOCAL_CACHE_DIR, `${safe}-${hash}.hindcast.json`);
}

async function storeLocal(deviceId: string, hash: string, data: StoredHindcast): Promise<void> {
    await mkdir(LOCAL_CACHE_DIR, { recursive: true });
    await writeFile(localPath(deviceId, hash), JSON.stringify(data), 'utf8');
}

async function readLocal(deviceId: string, hash: string): Promise<StoredHindcast | null> {
    try {
        return JSON.parse(await readFile(localPath(deviceId, hash), 'utf8')) as StoredHindcast;
    } catch {
        return null;
    }
}

/** Persist a reconstruction. Non-fatal: a store failure is logged, never thrown,
 *  so a flaky cache can never break forecasting (mirrors forecast caching). */
export async function storeHindcast(deviceId: string, hash: string, data: StoredHindcast): Promise<void> {
    try {
        if (!isBlobStorageConfigured()) {
            await storeLocal(deviceId, hash, data);
            return;
        }
        await put(blobPath(deviceId, hash), JSON.stringify(data), {
            access: 'private',
            addRandomSuffix: false,
            contentType: 'application/json',
            allowOverwrite: true,
        });
    } catch (err) {
        const m = err instanceof Error ? err.message : String(err);
        console.error(`[hindcast] failed to cache ${deviceId} (${hash}): ${m}`);
    }
}

export async function readStoredHindcast(deviceId: string, hash: string): Promise<StoredHindcast | null> {
    if (!isBlobStorageConfigured()) {
        return readLocal(deviceId, hash);
    }
    try {
        const r = await get(blobPath(deviceId, hash), { access: 'private', useCache: false });
        if (!r || r.statusCode !== 200) return null;
        return (await new Response(r.stream).json()) as StoredHindcast;
    } catch {
        return null;
    }
}

/* ----------------------------------------------------------------------------
 * Per-gap incremental cache (one blob per device).
 *
 * A single map of gapHash → cached bridge, so a recompute reuses every immutable
 * older gap and only re-bridges the recent/trailing one. Opaque JSON here; the
 * entry shape (GapCacheEntry) is owned by pathReconstruction. One read + one
 * write per compute regardless of gap count.
 * ------------------------------------------------------------------------- */
function gapCacheBlobPath(deviceId: string): string {
    return `hindcasts/${encodeURIComponent(deviceId)}.gapcache.json`;
}
function gapCacheLocalPath(deviceId: string): string {
    const safe = deviceId.replace(/[^a-zA-Z0-9._-]/g, '_');
    return join(LOCAL_CACHE_DIR, `${safe}.gapcache.json`);
}

/** Read the device's gap cache. Returns {} when none exists; never throws. */
export async function readGapCache(deviceId: string): Promise<Record<string, unknown>> {
    try {
        if (!isBlobStorageConfigured()) {
            return JSON.parse(await readFile(gapCacheLocalPath(deviceId), 'utf8')) as Record<string, unknown>;
        }
        const r = await get(gapCacheBlobPath(deviceId), { access: 'private', useCache: false });
        if (!r || r.statusCode !== 200) return {};
        return (await new Response(r.stream).json()) as Record<string, unknown>;
    } catch {
        return {};
    }
}

/** Persist the device's gap cache. Non-fatal on failure (logged, never thrown). */
export async function writeGapCache(deviceId: string, map: Record<string, unknown>): Promise<void> {
    try {
        const body = JSON.stringify(map);
        if (!isBlobStorageConfigured()) {
            await mkdir(LOCAL_CACHE_DIR, { recursive: true });
            await writeFile(gapCacheLocalPath(deviceId), body, 'utf8');
            return;
        }
        await put(gapCacheBlobPath(deviceId), body, {
            access: 'private',
            addRandomSuffix: false,
            contentType: 'application/json',
            allowOverwrite: true,
        });
    } catch (err) {
        const m = err instanceof Error ? err.message : String(err);
        console.error(`[hindcast] failed to write gap cache ${deviceId}: ${m}`);
    }
}
