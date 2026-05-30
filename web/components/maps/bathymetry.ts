/**
 * Swap the style's limited bathymetry for Mapbox's global `mapbox-bathymetry-v2`
 * tileset, so ocean depth shading shows at every zoom — including the globe /
 * low-zoom view, where the style's built-in 10 m tileset (minzoom 3) had no
 * tiles.
 *
 *   - Source `mapbox.mapbox-bathymetry-v2` (zoom 0–7, overzoomed above 7),
 *     source-layer `depth`, one nested polygon per `min_depth` band.
 *   - A single depth-graded fill, light shallow → deep navy, with deeper bands
 *     sorted on top so the nesting reads correctly.
 *   - The style's own bathymetry layers are hidden to avoid double-draw.
 *
 * Idempotent — safe to call on every `styledata` event.
 */
import type { Map, LayerSpecification } from 'mapbox-gl';

const SRC_ID = 'sl-bathymetry-v2';
const LAYER_ID = 'sl-bathymetry-v2';

const CAP_SRC_ID = 'sl-polar-cap';
const CAP_LAYER_ID = 'sl-polar-cap';

/* Web Mercator tiles stop at ~85.05°, so on the globe the North Pole is a
 * data hole (no water / no bathymetry). Fill it with a deep-ocean cap — the
 * Arctic around the pole is open ocean, so a single deep tone reads right.
 * Built as a lon/lat band [85°, 89.5°] spanning all longitudes, densified so
 * its edges reproject to clean parallels on the globe. */
function buildPolarCap(): GeoJSON.Feature {
    const ring: [number, number][] = [];
    for (let lon = -180; lon <= 180; lon += 10) ring.push([lon, 85]);
    for (let lon = 180; lon >= -180; lon -= 10) ring.push([lon, 89.5]);
    ring.push([-180, 85]);
    return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } };
}

/* Light continental shelf → deep navy trench. Mirrors the style's original
 * hsl(200, …) bathymetry palette, keyed to mapbox-bathymetry-v2's min_depth. */
const DEPTH_COLOR = [
    'interpolate', ['linear'], ['get', 'min_depth'],
    0, 'hsl(200, 28%, 95%)',
    200, 'hsl(200, 28%, 93%)',
    1000, 'hsl(200, 32%, 90%)',
    2000, 'hsl(200, 29%, 85%)',
    3000, 'hsl(200, 29%, 80%)',
    4000, 'hsl(200, 28%, 76%)',
    5000, 'hsl(200, 28%, 72%)',
    6000, 'hsl(200, 27%, 69%)',
    7000, 'hsl(200, 26%, 65%)',
    8000, 'hsl(200, 26%, 61%)',
    9000, 'hsl(200, 25%, 57%)',
    10000, 'hsl(200, 25%, 54%)',
] as unknown;

export function bathymetryAllZooms(map: Map): void {
    let layers: LayerSpecification[] = [];
    try { layers = (map.getStyle()?.layers ?? []) as LayerSpecification[]; } catch { return; }

    /* Hide the style's built-in bathymetry (limited tilesets) so we don't
     * double-draw over the global replacement. */
    for (const layer of layers) {
        const sl = (layer as { 'source-layer'?: string })['source-layer'] ?? '';
        if (layer.id === LAYER_ID) continue;
        if (/bathymetry|bathy/i.test(layer.id) || /bathymetry|bathy/i.test(sl)) {
            try { map.setLayoutProperty(layer.id, 'visibility', 'none'); } catch { /* ignore */ }
        }
    }

    /* Thin the coastline (`water-line`) stroke a touch — only if the base
     * style actually has that layer (guard avoids a Mapbox error event, which
     * a try/catch won't suppress). */
    if (map.getLayer('water-line')) {
        try {
            map.setPaintProperty('water-line', 'line-width', [
                'interpolate', ['linear'], ['zoom'],
                6, 0.5,
                10, 0.3,
                14, 0.3,
                18, 0.9,
            ] as never);
        } catch { /* ignore */ }
    }

    try {
        if (!map.getSource(SRC_ID)) {
            map.addSource(SRC_ID, { type: 'vector', url: 'mapbox://mapbox.mapbox-bathymetry-v2' });
        }
    } catch { /* source may already exist */ }

    try {
        if (!map.getLayer(LAYER_ID)) {
            /* Sit in the original bathymetry's slot (just above the ocean
             * `water` fill, below land/labels). Fall back to just above water. */
            const waterIdx = layers.findIndex(l => l.id === 'water');
            const beforeId = layers.some(l => l.id === 'bathymetry')
                ? 'bathymetry'
                : (waterIdx >= 0 ? layers[waterIdx + 1]?.id : undefined);
            map.addLayer({
                id: LAYER_ID,
                type: 'fill',
                source: SRC_ID,
                'source-layer': 'depth',
                layout: { 'fill-sort-key': ['get', 'min_depth'] as never },
                paint: {
                    'fill-antialias': false,
                    'fill-color': DEPTH_COLOR as never,
                },
            }, beforeId);
        }
    } catch { /* layer may already exist */ }

    /* Fill the Mercator polar hole. Placed ABOVE the `water-line` coastline
     * stroke so it also masks that layer's clip-edge ring at ~85° (the dark cap
     * on the globe) — while leaving water-lines untouched everywhere else. */
    try {
        if (!map.getSource(CAP_SRC_ID)) {
            map.addSource(CAP_SRC_ID, { type: 'geojson', data: buildPolarCap() });
        }
    } catch { /* source may already exist */ }
    try {
        if (!map.getLayer(CAP_LAYER_ID)) {
            const waterLineIdx = layers.findIndex(l => l.id === 'water-line');
            const waterIdx = layers.findIndex(l => l.id === 'water');
            const capBeforeId = waterLineIdx >= 0
                ? layers[waterLineIdx + 1]?.id
                : (waterIdx >= 0 ? layers[waterIdx + 1]?.id : undefined);
            map.addLayer({
                id: CAP_LAYER_ID,
                type: 'fill',
                source: CAP_SRC_ID,
                paint: {
                    /* Light ocean tone matching the base `water` fill so the cap
                     * reads as ocean continuing to the pole, not a dark disc. */
                    'fill-color': 'hsl(200, 40%, 90%)',
                    'fill-antialias': false,
                },
            }, capBeforeId);
        }
    } catch { /* layer may already exist */ }
}
