/**
 * Quiet the Mapbox basemap so balloon paths / forecast lines / gateway
 * fireflies are the visual subject.
 *
 *   - Hides state / province labels entirely.
 *   - Hides every road / motorway / bridge / tunnel layer.
 *   - Shrinks city + settlement label text by ~30% (opacity unchanged
 *     so legibility stays the same).
 *
 * Call once inside a Mapbox `load` handler. Safe to call again — the
 * underlying setLayoutProperty / setPaintProperty are idempotent.
 */
import type { Map, LayerSpecification } from 'mapbox-gl';

const HIDE_LABEL_PATTERNS = [
    /state-label/i,
    /province-label/i,
    /admin.*label.*1/i,    /* admin-1 label is the typical state/province pattern */
];

const HIDE_LINE_PATTERNS = [
    /road/i,
    /motorway/i,
    /street/i,
    /bridge/i,
    /tunnel/i,
];

const SHRINK_PATTERNS = [
    /settlement/i,         /* settlement-subdivision, settlement-major-label, etc. */
    /place/i,              /* city / town labels in some Mapbox styles */
];

/* How much smaller to render shrinkable label text. 0.7 = 70% of native. */
const SHRINK_SCALE = 0.7;

export function quietBasemapLabels(map: Map): void {
    let layers: LayerSpecification[] = [];
    try {
        layers = (map.getStyle()?.layers ?? []) as LayerSpecification[];
    } catch {
        return;
    }
    for (const layer of layers) {
        const id = layer.id;

        /* Hide non-symbol layers that match the road family — covers
         * the line/fill geometry, not just labels. */
        if (layer.type !== 'symbol' && HIDE_LINE_PATTERNS.some(re => re.test(id))) {
            try { map.setLayoutProperty(id, 'visibility', 'none'); } catch { /* ignore */ }
            continue;
        }

        if (layer.type !== 'symbol') continue;

        if (HIDE_LABEL_PATTERNS.some(re => re.test(id))) {
            try { map.setLayoutProperty(id, 'visibility', 'none'); } catch { /* ignore */ }
            continue;
        }

        /* Road shields / route numbers / highway names — hide too. */
        if (HIDE_LINE_PATTERNS.some(re => re.test(id))) {
            try { map.setLayoutProperty(id, 'visibility', 'none'); } catch { /* ignore */ }
            continue;
        }

        if (SHRINK_PATTERNS.some(re => re.test(id))) {
            try {
                const current = map.getLayoutProperty(id, 'text-size') as unknown;
                const scaled = scaleExpression(current, SHRINK_SCALE);
                /* The Mapbox typings narrow `text-size` to a few specific
                 * expression shapes; our return value is structurally
                 * equivalent but typed as `unknown` to allow any input. */
                map.setLayoutProperty(id, 'text-size', scaled as never);
            } catch { /* ignore */ }
        }
    }
}

/**
 * Multiply a Mapbox `text-size` (or any numeric layout value) by a scalar
 * while preserving the expression's top-level shape.
 *
 * Mapbox forbids `['zoom']` anywhere except at the top of `step` /
 * `interpolate` / a few other allowed roots — so we can't just wrap the
 * whole expression in `['*', expr, k]` when expr already contains a
 * zoom-driven interpolation. Instead we push the multiplier INTO each
 * leaf output value:
 *
 *   ['interpolate', ['linear'], ['zoom'], 5, 12, 10, 16]
 *     → ['interpolate', ['linear'], ['zoom'], 5, ['*', 12, k], 10, ['*', 16, k]]
 *
 *   ['step', ['zoom'], 10, 5, 12, 10, 14]
 *     → ['step', ['zoom'], ['*', 10, k], 5, ['*', 12, k], 10, ['*', 14, k]]
 *
 * Plain numbers and constant arrays are multiplied directly.
 */
type Expr = unknown;
function scaleExpression(current: Expr, k: number): Expr {
    if (typeof current === 'number') return current * k;
    if (current === undefined || current === null) return current;
    if (!Array.isArray(current)) {
        /* Some other expression form we don't know how to scale safely —
         * leave it alone. */
        return current;
    }
    const op = current[0];

    if (op === 'interpolate' || op === 'interpolate-hcl' || op === 'interpolate-lab') {
        /* Shape: [op, interpType, input, stop_in_1, stop_out_1, stop_in_2, stop_out_2, …] */
        const out: Expr[] = [op, current[1], current[2]];
        for (let i = 3; i < current.length; i += 2) {
            out.push(current[i]);                                    /* stop input */
            out.push(scaleExpression(current[i + 1] as Expr, k));    /* stop output */
        }
        return out;
    }

    if (op === 'step') {
        /* Shape: [op, input, default_out, stop_in_1, stop_out_1, stop_in_2, stop_out_2, …] */
        const out: Expr[] = [op, current[1], scaleExpression(current[2] as Expr, k)];
        for (let i = 3; i < current.length; i += 2) {
            out.push(current[i]);
            out.push(scaleExpression(current[i + 1] as Expr, k));
        }
        return out;
    }

    /* Last-resort fallback — wrap and let Mapbox tell us if it's bad.
     * Works for purely-data expressions (e.g. `['get', 'size']`). */
    return ['*', current, k];
}
