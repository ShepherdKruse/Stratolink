/**
 * Deep links into earth.nullschool.net — wind at isobaric levels.
 * @see https://earth.nullschool.net/
 */

export const NULLSCHOOL_PRESSURE_LEVELS = [
    { id: '1000hPa', label: '1000 hPa', approxAltM: 100 },
    { id: '850hPa', label: '850 hPa', approxAltM: 1500 },
    { id: '700hPa', label: '700 hPa', approxAltM: 3000 },
    { id: '500hPa', label: '500 hPa', approxAltM: 5500 },
    { id: '250hPa', label: '250 hPa', approxAltM: 10500 },
    { id: '70hPa', label: '70 hPa', approxAltM: 18000 },
    { id: '10hPa', label: '10 hPa', approxAltM: 30000 },
] as const;

export type NullschoolPressureId = (typeof NULLSCHOOL_PRESSURE_LEVELS)[number]['id'];

const LEVEL_HPA: { id: NullschoolPressureId; hpa: number }[] = NULLSCHOOL_PRESSURE_LEVELS.map(
    (l) => ({ id: l.id, hpa: parseInt(l.id, 10) }),
);

/** Pick the closest standard isobaric level for a barometric reading (hPa). */
export function pressureHpaToNullschoolLevel(hPa: number | null | undefined): NullschoolPressureId {
    if (hPa == null || !Number.isFinite(hPa) || hPa <= 0) return '250hPa';
    let best: NullschoolPressureId = '250hPa';
    let bestDiff = Infinity;
    for (const { id, hpa } of LEVEL_HPA) {
        const diff = Math.abs(hpa - hPa);
        if (diff < bestDiff) {
            bestDiff = diff;
            best = id;
        }
    }
    return best;
}

export type NullschoolViewOptions = {
    lon: number;
    lat: number;
    /** orthographic zoom — higher = closer (nullschool convention ~2–6 for regional). */
    zoom?: number;
    level?: NullschoolPressureId;
    /** ISO time for historical view; omit for live model. */
    at?: Date | null;
};

/**
 * Build a nullschool URL centered on a point at the given pressure level.
 * Uses orthographic projection for regional balloon context.
 */
export function buildNullschoolWindUrl(opts: NullschoolViewOptions): string {
    const level = opts.level ?? '250hPa';
    const zoom = opts.zoom ?? 4;
    const lon = opts.lon.toFixed(2);
    const lat = opts.lat.toFixed(2);

    let datePart = 'current';
    if (opts.at && !Number.isNaN(opts.at.getTime())) {
        const y = opts.at.getUTCFullYear();
        const mo = String(opts.at.getUTCMonth() + 1).padStart(2, '0');
        const d = String(opts.at.getUTCDate()).padStart(2, '0');
        const h = String(opts.at.getUTCHours()).padStart(2, '0');
        datePart = `${y}/${mo}/${d}/${h}00Z`;
    }

    return `https://earth.nullschool.net/#${datePart}/wind/isobaric/${level}/orthographic=${lon},${lat},${zoom}`;
}

export const NULLSCHOOL_HOME = 'https://earth.nullschool.net/';
