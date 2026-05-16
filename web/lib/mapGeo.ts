/** Shared checks for map layers and Mapbox. */

export function isValidWgs84Point(lat: unknown, lon: unknown): boolean {
    if (typeof lat !== 'number' || typeof lon !== 'number') return false;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

/**
 * Valid WGS84 that is unlikely to be a DB / NOGPS sentinel. Rejects Null Island (0°, 0°)
 * before coercing missing lat/lon to 0 via Number(null).
 */
export function isUsableGpsCoordinate(lat: unknown, lon: unknown): boolean {
    if (!isValidWgs84Point(lat, lon)) return false;
    return !(lat === 0 && lon === 0);
}

export function isWebGLAvailable(): boolean {
    if (typeof window === 'undefined') return false;
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
        return !!gl;
    } catch {
        return false;
    }
}
