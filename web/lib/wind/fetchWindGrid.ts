/* Shared wind-cube geometry helpers. The Open-Meteo grid fetchers that used to
 * live here were deleted in Oct 2026: every wind field now comes from the NOAA
 * cubes built by scripts/gfs_ingest.py, and nothing may call a live weather API. */

/** Bounding box of a wind cube, in degrees. `lonMax` may exceed 180 for a box
 *  that crosses the antimeridian (longitudes stay continuous). */
export type WindGridBounds = {
    latMin: number;
    latMax: number;
    lonMin: number;
    lonMax: number;
};

const GFS_PRESSURE_LEVELS_HPA = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 70, 50, 30];

/** Snap a telemetry pressure to the nearest standard GFS isobaric level. The
 *  ingest blends the two bracketing levels to the actual float pressure, so this
 *  only decides the level the forecast reports and the reconstruction cache keys on. */
export function snapPressureHpa(hpa: number): number {
    if (!Number.isFinite(hpa) || hpa <= 0) return 250;
    let best = GFS_PRESSURE_LEVELS_HPA[0];
    let bestDiff = Math.abs(hpa - best);
    for (const level of GFS_PRESSURE_LEVELS_HPA) {
        const d = Math.abs(hpa - level);
        if (d < bestDiff) {
            best = level;
            bestDiff = d;
        }
    }
    return best;
}
