/**
 * Imperative twin of <GatewayLayer />. For maps built on raw mapbox-gl
 * (rather than react-map-gl), call this once inside `map.on('load', …)`
 * to add the same coverage-union polygon + firefly stack of layers.
 *
 * Fetches `/ttnmapper-gateways.json` and `/ttnmapper-coverage.json` once
 * each, sharing the parsed data with <GatewayLayer />'s module-level
 * memos (we both populate `_stratolink…` slots on globalThis so re-renders
 * / map remounts skip the fetch).
 */
import type { Map } from 'mapbox-gl';
import type { MultiPolygon, Polygon } from 'geojson';

interface RawGateway {
    lat: number;
    lon: number;
    net: 'v2' | 'v3';
}

type CoverageGeometry = MultiPolygon | Polygon;

interface GatewaysGlobal {
    _stratolinkGateways?: RawGateway[];
    _stratolinkCoverage?: CoverageGeometry;
}

async function loadGateways(): Promise<RawGateway[] | null> {
    const g = globalThis as unknown as GatewaysGlobal;
    if (g._stratolinkGateways) return g._stratolinkGateways;
    try {
        const r = await fetch('/ttnmapper-gateways.json');
        if (!r.ok) return null;
        const body = (await r.json()) as { gateways: RawGateway[] };
        g._stratolinkGateways = body.gateways ?? [];
        return g._stratolinkGateways;
    } catch {
        return null;
    }
}

async function loadCoverage(): Promise<CoverageGeometry | null> {
    const g = globalThis as unknown as GatewaysGlobal;
    if (g._stratolinkCoverage) return g._stratolinkCoverage;
    try {
        const r = await fetch('/ttnmapper-coverage.json');
        if (!r.ok) return null;
        const body = (await r.json()) as { coverage: CoverageGeometry };
        if (body.coverage) g._stratolinkCoverage = body.coverage;
        return body.coverage ?? null;
    } catch {
        return null;
    }
}

interface AddGatewayLayersOptions {
    /** Stop adding layers if the map has been torn down before fetch resolves. */
    isMounted?: () => boolean;
}

export async function addGatewayLayersToMap(
    map: Map,
    opts: AddGatewayLayersOptions = {},
): Promise<void> {
    const [points, coverage] = await Promise.all([loadGateways(), loadCoverage()]);
    if (opts.isMounted && !opts.isMounted()) return;
    /* Bail if the map was removed mid-fetch. */
    try {
        if (!map.getStyle()) return;
    } catch {
        return;
    }

    /* Coverage union — added FIRST so the firefly points draw on top. */
    if (coverage && !map.getSource('tm-coverage')) {
        map.addSource('tm-coverage', {
            type: 'geojson',
            data: { type: 'Feature', geometry: coverage, properties: {} },
        });
        map.addLayer({
            id: 'tm-coverage-fill',
            source: 'tm-coverage',
            type: 'fill',
            paint: {
                'fill-color': '#5eead4',
                'fill-opacity': 0.05,
            },
        });
        map.addLayer({
            id: 'tm-coverage-outline',
            source: 'tm-coverage',
            type: 'line',
            paint: {
                'line-color': 'rgba(94, 234, 212, 0.28)',
                'line-width': 0.6,
            },
        });
    }

    if (!points || points.length === 0) return;
    if (map.getSource('tm-gateways')) return;

    const geojson = {
        type: 'FeatureCollection' as const,
        features: points.map(g => ({
            type: 'Feature' as const,
            geometry: { type: 'Point' as const, coordinates: [g.lon, g.lat] as [number, number] },
            properties: { net: g.net },
        })),
    };
    map.addSource('tm-gateways', { type: 'geojson', data: geojson });

    map.addLayer({
        id: 'tm-gateways-halo',
        source: 'tm-gateways',
        type: 'circle',
        paint: {
            'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                3, 3, 6, 4.5, 10, 8, 14, 13,
            ],
            'circle-color': ['match', ['get', 'net'], 'v3', '#5eead4', 'v2', '#94a3b8', '#94a3b8'],
            'circle-opacity': 0.08,
            'circle-blur': 0.9,
        },
    });

    map.addLayer({
        id: 'tm-gateways-glow',
        source: 'tm-gateways',
        type: 'circle',
        paint: {
            'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                3, 1.4, 6, 2.2, 10, 3.6, 14, 6,
            ],
            'circle-color': ['match', ['get', 'net'], 'v3', '#5eead4', 'v2', '#94a3b8', '#94a3b8'],
            'circle-opacity': 0.18,
            'circle-blur': 0.4,
        },
    });

    map.addLayer({
        id: 'tm-gateways-core',
        source: 'tm-gateways',
        type: 'circle',
        paint: {
            'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                3, 0.5, 6, 0.8, 10, 1.4, 14, 2.4,
            ],
            'circle-color': ['match', ['get', 'net'], 'v3', '#ccfbf1', 'v2', '#cbd5e1', '#cbd5e1'],
            'circle-opacity': 0.5,
        },
    });
}
