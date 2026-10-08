import type { Map } from 'mapbox-gl';

/** Reuse tiles already supplied by the basemap's composite vector source. */
export function ensureVectorSource(map: Map, fallbackId: string, tileset: string): string {
    for (const [id, source] of Object.entries(map.getStyle()?.sources ?? {})) {
        if (source.type !== 'vector' || !source.url?.startsWith('mapbox://')) continue;
        const tilesets = source.url.slice('mapbox://'.length).split('?')[0].split(',');
        if (tilesets.includes(tileset)) return id;
    }
    if (!map.getSource(fallbackId)) map.addSource(fallbackId, { type: 'vector', url: `mapbox://${tileset}` });
    return fallbackId;
}
