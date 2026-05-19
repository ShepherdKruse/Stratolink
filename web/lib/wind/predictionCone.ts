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
 * @deprecated Prefer buildPathCorridorEnvelope — hull often leaves the central path on an edge.
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

/**
 * Symmetric corridor around the central forecast path from cross-track ensemble spread
 * at each forecast step (central path stays inside the band, not on a hull edge).
 */
export function buildPathCorridorEnvelope(
    centralPath: Array<[number, number]>,
    memberPaths: Array<Array<[number, number]>>,
    minHalfWidthDeg = 0.06,
): Array<[number, number]> {
    const n = centralPath.length;
    if (n < 2) return [];

    const aligned = memberPaths.filter((p) => p.length === n);
    const allAtStep = [centralPath, ...aligned];

    const left: Array<[number, number]> = [];
    const right: Array<[number, number]> = [];

    for (let i = 0; i < n; i++) {
        const [cLon, cLat] = centralPath[i];
        const prev = centralPath[Math.max(0, i - 1)];
        const next = centralPath[Math.min(n - 1, i + 1)];
        const cosLat = Math.cos((cLat * Math.PI) / 180);

        const tLon = (next[0] - prev[0]) * cosLat;
        const tLat = next[1] - prev[1];
        const tLen = Math.hypot(tLon, tLat) || 1e-9;
        const nLon = -tLat / tLen;
        const nLat = tLon / tLen;

        const tFrac = i / Math.max(1, n - 1);
        let halfWidth = minHalfWidthDeg + tFrac * 0.12;

        for (const path of allAtStep) {
            const [lon, lat] = path[i];
            const dLon = (lon - cLon) * cosLat;
            const dLat = lat - cLat;
            const perp = Math.abs(dLon * nLon + dLat * nLat);
            halfWidth = Math.max(halfWidth, perp + minHalfWidthDeg * 0.35);
        }

        left.push([cLon + (nLon * halfWidth) / cosLat, cLat + nLat * halfWidth]);
        right.push([cLon - (nLon * halfWidth) / cosLat, cLat - nLat * halfWidth]);
    }

    return [...left, ...right.reverse(), left[0]!];
}
