/**
 * Code-only shaded-relief basemap, layered onto a stock Mapbox base style
 * (light-v11) — no Mapbox Studio style required.
 *
 * Reproduces the look we'd built in Studio, but entirely from public Mapbox
 * tilesets so it loads with any token and lives in the repo:
 *   - Recolor the gray default ocean to a light blue.
 *   - Add terrain hillshade from `mapbox.mapbox-terrain-v2` (the same `level`
 *     bands the Studio style used), white highlights + neutral (de-yellowed)
 *     shadows, sitting just under the water so it shades land only.
 *
 * (Ocean bathymetry + the polar cap are added separately in `bathymetry.ts`.)
 *
 * Idempotent — safe to call on every `styledata` event.
 */
import type { Map, LayerSpecification } from 'mapbox-gl';

const TERRAIN_SRC = 'sl-terrain';

type Scheme = 'light' | 'dark';

/* Relief tones + base water per basemap. Light: white highlights / cool-gray
 * shadows over near-white land. Dark: cool-gray highlights / near-black shadows
 * over the dark basemap, and a deep blue-gray ocean instead of the light blue. */
const RELIEF: Record<Scheme, { highlight: string; shadow: string; water: string; waterway: string }> = {
    light: {
        highlight: 'hsl(0, 0%, 100%)',
        shadow: 'hsl(210, 12%, 30%)',
        water: 'hsl(200, 42%, 95%)',
        waterway: 'hsl(200, 25%, 82%)',
    },
    dark: {
        highlight: 'hsl(210, 14%, 52%)',
        shadow: 'hsl(214, 30%, 5%)',
        water: 'hsl(212, 30%, 15%)',
        waterway: 'hsl(210, 18%, 30%)',
    },
};

/* terrain-v2 `hillshade` bands, mirroring the Studio relief. Shadows nudged a
 * touch stronger than Studio (0.07/0.08) since light-v11's land is near-white,
 * where the white highlights barely register. */
type Band = { id: string; level: number; kind: 'highlight' | 'shadow'; opacity: number; fade: number };
const BANDS: Band[] = [
    { id: 'sl-hs-hi-bright', level: 94, kind: 'highlight', opacity: 0.15, fade: 18 },
    { id: 'sl-hs-hi-med', level: 90, kind: 'highlight', opacity: 0.15, fade: 18 },
    { id: 'sl-hs-sh-faint', level: 89, kind: 'shadow', opacity: 0.10, fade: 17 },
    { id: 'sl-hs-sh-med', level: 78, kind: 'shadow', opacity: 0.11, fade: 17 },
    { id: 'sl-hs-sh-dark', level: 67, kind: 'shadow', opacity: 0.13, fade: 17 },
    { id: 'sl-hs-sh-extreme', level: 56, kind: 'shadow', opacity: 0.13, fade: 17 },
];

function set(map: Map, id: string, prop: string, value: unknown): void {
    /* Guard with getLayer: setPaintProperty on a missing layer fires a Mapbox
     * error event (logged to console) that a try/catch wouldn't suppress. */
    if (!map.getLayer(id)) return;
    try { map.setPaintProperty(id, prop as never, value as never); } catch { /* ignore */ }
}

export function applyBaseStyle(map: Map, scheme: Scheme = 'light'): void {
    const relief = RELIEF[scheme];
    let layers: LayerSpecification[] = [];
    try { layers = (map.getStyle()?.layers ?? []) as LayerSpecification[]; } catch { return; }

    /* Ocean / rivers recolored per theme (the stock styles ship them gray /
     * near-black). Bathymetry draws over the open ocean; this base tone covers
     * lakes, rivers, shelf. */
    set(map, 'water', 'fill-color', relief.water);
    set(map, 'waterway', 'line-color', relief.waterway);

    /* Terrain hillshade from the public terrain-v2 tileset. */
    try {
        if (!map.getSource(TERRAIN_SRC)) {
            map.addSource(TERRAIN_SRC, { type: 'vector', url: 'mapbox://mapbox.mapbox-terrain-v2' });
        }
    } catch { /* source may already exist */ }

    /* Insert under `water` so the relief shades land, ocean stays clean. */
    const beforeId = layers.find(l => l.id === 'water')?.id;
    for (const b of BANDS) {
        try {
            if (map.getLayer(b.id)) continue;
            map.addLayer({
                id: b.id,
                type: 'fill',
                source: TERRAIN_SRC,
                'source-layer': 'hillshade',
                filter: ['==', ['get', 'level'], b.level],
                paint: {
                    'fill-color': b.kind === 'highlight' ? relief.highlight : relief.shadow,
                    'fill-antialias': false,
                    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 15, b.opacity, b.fade, 0] as never,
                },
            }, beforeId);
        } catch { /* layer may already exist */ }
    }
}
