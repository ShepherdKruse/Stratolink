/** Build uncertainty polygon around a predicted path (growing half-width over time). */
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
