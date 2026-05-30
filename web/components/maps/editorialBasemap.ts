/**
 * Re-paint the Mapbox light basemap into a quiet, custom editorial cartography
 * palette — so the map reads as a designed atlas plate, not "default Mapbox."
 *
 * Cool neutral land, a muted desaturated water, hairline ink admin borders,
 * and restrained ink labels with a paper halo. Pairs with quietBasemapLabels
 * (which hides roads + state labels). All setters are idempotent, so it's safe
 * to call on every `styledata` event.
 */
import type { Map, LayerSpecification } from 'mapbox-gl';

const PALETTE = {
    land:        '#eaeaeb',   /* near-neutral light gray */
    landAlt:     '#e5e5e6',   /* parks / landuse — barely distinct */
    water:       '#d2d3d4',   /* desaturated neutral gray, a touch darker than land */
    waterLine:   '#bcbdbf',
    border:      'rgba(15, 17, 22, 0.34)',
    borderSub:   'rgba(15, 17, 22, 0.14)',
    labelText:   '#3c3e42',   /* neutral ink */
    labelTextDim:'#797a7e',
    labelHalo:   '#ededee',   /* neutral near-white */
};

function set(map: Map, id: string, prop: string, value: unknown): void {
    try { map.setPaintProperty(id, prop as never, value as never); } catch { /* layer lacks prop */ }
}

export function editorialBasemap(map: Map): void {
    let layers: LayerSpecification[] = [];
    try { layers = (map.getStyle()?.layers ?? []) as LayerSpecification[]; } catch { return; }

    for (const layer of layers) {
        const id = layer.id;
        const type = layer.type;

        if (type === 'background') {
            set(map, id, 'background-color', PALETTE.land);
            continue;
        }

        if (type === 'fill') {
            if (/water|ocean|sea|bathymetry/i.test(id)) {
                set(map, id, 'fill-color', PALETTE.water);
                set(map, id, 'fill-opacity', 1);
            } else if (/national-park|park|landuse|landcover|wood|forest|grass|pitch|sand|glacier/i.test(id)) {
                set(map, id, 'fill-color', PALETTE.landAlt);
                set(map, id, 'fill-opacity', 0.55);
            } else if (/^land$|land-/i.test(id)) {
                set(map, id, 'fill-color', PALETTE.land);
            }
            continue;
        }

        if (type === 'line') {
            if (/water|river|waterway|canal|stream/i.test(id)) {
                set(map, id, 'line-color', PALETTE.waterLine);
                set(map, id, 'line-opacity', 0.5);
            } else if (/admin-0|country.*boundary|^admin-0-boundary$/i.test(id)) {
                set(map, id, 'line-color', PALETTE.border);
            } else if (/admin/i.test(id)) {
                set(map, id, 'line-color', PALETTE.borderSub);
            }
            continue;
        }

        if (type === 'symbol') {
            /* Country labels get the darker ink; everything else a softer ink.
             * Halo matches the land so labels sit cleanly on the plate. */
            const dim = !/country|continent|ocean|sea|water/i.test(id);
            set(map, id, 'text-color', dim ? PALETTE.labelTextDim : PALETTE.labelText);
            set(map, id, 'text-halo-color', PALETTE.labelHalo);
            set(map, id, 'text-halo-width', 1.1);
            set(map, id, 'text-halo-blur', 0.4);
        }
    }
}
