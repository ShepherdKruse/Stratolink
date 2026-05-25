/**
 * Imperative twin of <GatewayLayer />. For maps built on raw mapbox-gl
 * (rather than react-map-gl), call this once inside `map.on('load', …)`
 * to add the same additive heat field + crisp points + edgeless coverage
 * underlay.
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

    /* Insert the wash + heat field beneath the basemap's first symbol
     * (label) layer so city / country names stay readable on top. */
    let beforeId: string | undefined;
    try {
        beforeId = map.getStyle()?.layers?.find(l => l.type === 'symbol')?.id;
    } catch {
        beforeId = undefined;
    }

    /* Coverage union — edgeless, very-low-opacity true-km reach beneath the
     * heat field. No outline (the hard edge is what quilted the view). */
    if (coverage && !map.getSource('tm-coverage')) {
        map.addSource('tm-coverage', {
            type: 'geojson',
            data: { type: 'Feature', geometry: coverage, properties: {} },
        });
        map.addLayer(
            {
                id: 'tm-coverage-fill',
                source: 'tm-coverage',
                type: 'fill',
                paint: {
                    'fill-color': '#3fb8a0',
                    'fill-opacity': 0.06,
                    'fill-antialias': false,
                },
            },
            beforeId,
        );
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

    /* Additive heat field — overlapping gateways sum into a brighter teal
     * glow; isolated ones stay faint. Beneath labels. */
    map.addLayer(
        {
            id: 'tm-gateway-coverage',
            source: 'tm-gateways',
            type: 'heatmap',
            paint: {
                'heatmap-weight': 1,
                /* Low intensity so ultra-dense regions (Europe) don't clamp the
                 * whole continent to the top of the ramp. */
                'heatmap-intensity': [
                    'interpolate', ['linear'], ['zoom'],
                    2, 0.25, 5, 0.5, 10, 0.9,
                ],
                /* Gentle ramp, soft top alpha → glow not paint. */
                'heatmap-color': [
                    'interpolate', ['linear'], ['heatmap-density'],
                    0, 'rgba(63,184,160,0)',
                    0.2, 'rgba(63,184,160,0.08)',
                    0.45, 'rgba(63,184,160,0.16)',
                    0.7, 'rgba(80,200,180,0.24)',
                    1, 'rgba(120,225,205,0.32)',
                ],
                'heatmap-radius': [
                    'interpolate', ['linear'], ['zoom'],
                    2, 10, 5, 26, 10, 60,
                ],
                'heatmap-opacity': [
                    'interpolate', ['linear'], ['zoom'],
                    2, 0.6, 6, 0.85,
                ],
            },
        },
        beforeId,
    );

    /* Crisp bright-teal points on top — gateway locations as data. Hidden on
     * the world / globe view, fading in as you zoom to continental / local. */
    map.addLayer({
        id: 'tm-gateway-points',
        source: 'tm-gateways',
        type: 'circle',
        paint: {
            'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                4, 1.6, 8, 4,
            ],
            'circle-color': '#5fd4bc',
            'circle-stroke-color': 'rgba(95,212,188,0.5)',
            'circle-stroke-width': 1,
            'circle-opacity': [
                'interpolate', ['linear'], ['zoom'],
                4, 0, 6, 0.85,
            ],
        },
    });
}
