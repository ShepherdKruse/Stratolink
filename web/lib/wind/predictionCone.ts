/** Build uncertainty polygon around a predicted path (growing half-width over time). @deprecated Use buildEnsembleEnvelope */
export function buildPredictionCone(path: Array<[number, number]>): [number, number][] {
    if (path.length < 2) return [];

    const right: [number, number][] = [];
    const left: [number, number][] = [];

    for (let i = 0; i < path.length; i++) {
        const [lon, lat] = path[i];
        const t = i / (path.length - 1);
        const halfWidth = 0.3 + t * 3.2;
        const cosLat = Math.cos((lat * Math.PI) / 180);
        right.push([lon + (halfWidth / Math.max(cosLat, 0.2)) * 0.6, lat - halfWidth * 0.25]);
        left.push([lon - (halfWidth / Math.max(cosLat, 0.2)) * 0.6, lat + halfWidth * 0.25]);
    }

    return [...right, ...left.reverse(), right[0]];
}

/** Convex hull (monotone chain) for [lon, lat] points. */
function convexHull(points: Array<[number, number]>): Array<[number, number]> {
    const pts = [...points].sort((a, b) => (a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]));
    if (pts.length <= 2) return pts;

    const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
        (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

    const lower: Array<[number, number]> = [];
    for (const p of pts) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
            lower.pop();
        }
        lower.push(p);
    }

    const upper: Array<[number, number]> = [];
    for (let i = pts.length - 1; i >= 0; i--) {
        const p = pts[i];
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
            upper.pop();
        }
        upper.push(p);
    }

    lower.pop();
    upper.pop();
    return [...lower, ...upper];
}

/** Expand hull vertices slightly outward from centroid (degrees). */
function bufferHull(hull: Array<[number, number]>, bufferDeg: number): Array<[number, number]> {
    if (hull.length < 3 || bufferDeg <= 0) return hull;
    const cx = hull.reduce((s, p) => s + p[0], 0) / hull.length;
    const cy = hull.reduce((s, p) => s + p[1], 0) / hull.length;
    return hull.map(([lon, lat]) => {
        const dx = lon - cx;
        const dy = lat - cy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1e-9;
        const scale = 1 + bufferDeg / dist;
        return [cx + dx * scale, cy + dy * scale];
    });
}

/**
 * Uncertainty region from ensemble drift paths (convex hull of all member points).
 */
export function buildEnsembleEnvelope(
    paths: Array<Array<[number, number]>>,
    bufferDeg = 0.15,
): Array<[number, number]> {
    const all = paths.flat().filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
    if (all.length < 3) {
        const fallback = paths[0];
        return fallback?.length ? buildPredictionCone(fallback) : [];
    }

    const hull = convexHull(all);
    if (hull.length < 3) return hull;
    const closed = bufferHull(hull, bufferDeg);
    return [...closed, closed[0]];
}
