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
            /* Scale text-size by SHRINK_SCALE. The size can be a number,
             * a `['interpolate', …]` expression, or a `['step', …]`
             * expression depending on the style. Wrap whatever's there
             * in a multiplication. */
            try {
                const current = map.getLayoutProperty(id, 'text-size');
                if (current !== undefined && current !== null) {
                    map.setLayoutProperty(id, 'text-size', ['*', current, SHRINK_SCALE]);
                }
            } catch { /* ignore */ }
        }
    }
}
