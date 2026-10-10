import { get, put } from '@vercel/blob';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { StratolinkForecast } from './forecastTypes';

function blobPath(deviceId: string): string {
    return `forecasts/${encodeURIComponent(deviceId)}.json`;
}

export function isBlobStorageConfigured(): boolean {
    return Boolean(process.env.BLOB_READ_WRITE_TOKEN);
}

/* ----------------------------------------------------------------------------
 * Local filesystem fallback.
 *
 * When Blob isn't configured (local dev without BLOB_READ_WRITE_TOKEN), persist
 * computed forecasts to a gitignored cache directory instead, so a forecast
 * computed once from local cubes (scripts/forecast_local.ts) can be re-read
 * without recomputing.
 * ------------------------------------------------------------------------- */
const LOCAL_CACHE_DIR = join(process.cwd(), '.forecast-cache');

function localPath(deviceId: string): string {
    /* Keep the filename filesystem-safe; device IDs are slugs but be defensive. */
    const safe = deviceId.replace(/[^a-zA-Z0-9._-]/g, '_');
    return join(LOCAL_CACHE_DIR, `${safe}.json`);
}

async function storeForecastLocal(deviceId: string, forecast: StratolinkForecast): Promise<string> {
    await mkdir(LOCAL_CACHE_DIR, { recursive: true });
    const path = localPath(deviceId);
    await writeFile(path, JSON.stringify(forecast), 'utf8');
    return path;
}

async function readStoredForecastLocal(deviceId: string): Promise<StratolinkForecast | null> {
    try {
        const raw = await readFile(localPath(deviceId), 'utf8');
        return JSON.parse(raw) as StratolinkForecast;
    } catch {
        return null;
    }
}

export async function storeForecast(deviceId: string, forecast: StratolinkForecast): Promise<string | null> {
    if (!isBlobStorageConfigured()) {
        return storeForecastLocal(deviceId, forecast);
    }
    const pathname = blobPath(deviceId);
    const blob = await put(pathname, JSON.stringify(forecast), {
        access: 'private',
        addRandomSuffix: false,
        contentType: 'application/json',
        allowOverwrite: true,
    });
    return blob.url;
}

export async function readStoredForecast(deviceId: string): Promise<StratolinkForecast | null> {
    if (!isBlobStorageConfigured()) {
        return readStoredForecastLocal(deviceId);
    }
    try {
        /* Private store: read via the authenticated `get` (token from env), not a
         * public URL fetch. Returns null when the blob doesn't exist. */
        const r = await get(blobPath(deviceId), { access: 'private', useCache: false });
        if (!r || r.statusCode !== 200) return null;
        return (await new Response(r.stream).json()) as StratolinkForecast;
    } catch {
        return null;
    }
}
