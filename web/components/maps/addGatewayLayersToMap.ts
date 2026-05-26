/**
 * Imperative twin of <GatewayLayer />. For maps built on raw mapbox-gl
 * (rather than react-map-gl), call this once inside `map.on('load', …)`
 * to add the same coverage-union polygons (150 km filled, 250 km
 * dashed outline).
 *
 * Fetches `/ttnmapper-coverage.json` + `/ttnmapper-coverage-outer.json`
 * once each, sharing the parsed data with <GatewayLayer />'s module-
 * level memos via `_stratolink…` slots on globalThis so re-renders /
 * map remounts skip the fetch.
 */
import type { Map } from 'mapbox-gl';
import type { MultiPolygon, Polygon } from 'geojson';

type CoverageGeometry = MultiPolygon | Polygon;

interface GatewaysGlobal {
    _stratolinkCoverage?: CoverageGeometry;
    _stratolinkCoverageOuter?: CoverageGeometry;
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

async function loadCoverageOuter(): Promise<CoverageGeometry | null> {
    const g = globalThis as unknown as GatewaysGlobal;
    if (g._stratolinkCoverageOuter) return g._stratolinkCoverageOuter;
    try {
        const r = await fetch('/ttnmapper-coverage-outer.json');
        if (!r.ok) return null;
        const body = (await r.json()) as { coverage: CoverageGeometry };
        if (body.coverage) g._stratolinkCoverageOuter = body.coverage;
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
    const [coverage, coverageOuter] = await Promise.all([
        loadCoverage(),
        loadCoverageOuter(),
    ]);
    if (opts.isMounted && !opts.isMounted()) return;
    /* Bail if the map was removed mid-fetch. */
    try {
        if (!map.getStyle()) return;
    } catch {
        return;
    }

    /* Outer (250 km) coverage union — outline only. Added FIRST so the
     * inner 150 km outline draws on top of it. */
    if (coverageOuter && !map.getSource('tm-coverage-outer')) {
        map.addSource('tm-coverage-outer', {
            type: 'geojson',
            data: { type: 'Feature', geometry: coverageOuter, properties: {} },
        });
        map.addLayer({
            id: 'tm-coverage-outer-outline',
            source: 'tm-coverage-outer',
            type: 'line',
            paint: {
                'line-color': 'rgba(94, 234, 212, 0.35)',
                'line-width': 0.8,
                'line-dasharray': [3, 2],
            },
        });
    }

    /* Inner (150 km) coverage union — fill + outline. */
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
}
