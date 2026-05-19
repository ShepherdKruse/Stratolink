import { head, put } from '@vercel/blob';
import type { StratolinkForecast } from './forecastTypes';

function blobPath(deviceId: string): string {
    return `forecasts/${encodeURIComponent(deviceId)}.json`;
}

export function isBlobStorageConfigured(): boolean {
    return Boolean(process.env.BLOB_READ_WRITE_TOKEN);
}

export async function storeForecast(deviceId: string, forecast: StratolinkForecast): Promise<string | null> {
    if (!isBlobStorageConfigured()) return null;
    const pathname = blobPath(deviceId);
    const blob = await put(pathname, JSON.stringify(forecast), {
        access: 'public',
        addRandomSuffix: false,
        contentType: 'application/json',
        allowOverwrite: true,
    });
    return blob.url;
}

export async function readStoredForecast(deviceId: string): Promise<StratolinkForecast | null> {
    if (!isBlobStorageConfigured()) return null;
    try {
        const meta = await head(blobPath(deviceId));
        const res = await fetch(meta.url, { next: { revalidate: 60 } });
        if (!res.ok) return null;
        return (await res.json()) as StratolinkForecast;
    } catch {
        return null;
    }
}
