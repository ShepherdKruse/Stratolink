/**
 * TTN gateway coverage layer.
 *
 * Renders two static snapshots from ttnmapper.org:
 *
 *   1. `public/ttnmapper-gateways.json` — ~14k gateway points. Each is
 *      drawn as a 3-layer firefly (outer halo, mid glow, crisp core) so
 *      the dot reads as soft ambient texture against the busy forecast /
 *      track layers, not a hard pin.
 *
 *   2. `public/ttnmapper-coverage.json` — the **union** of 250 km buffers
 *      around every gateway, pre-computed offline as one MultiPolygon. We
 *      render this as a single soft fill + outline. Overlapping rings in
 *      dense regions no longer compound into a wash of color; instead the
 *      regions of coverage read as one connected blob and the *gaps*
 *      (where reception isn't possible) stand out.
 *
 * Both refreshed by `npm run gateways:refresh`. Loads lazily on first
 * mount via module-level memos shared across instances.
 *
 * Usage: drop `<GatewayLayer />` inside a react-map-gl `<Map>`.
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { Layer, Source } from 'react-map-gl/mapbox';
import type { Feature, MultiPolygon, Polygon } from 'geojson';

interface RawGateway {
    lat: number;
    lon: number;
    /** 'v3' (TTS v3) or 'v2' (legacy TTN v2). */
    net: 'v2' | 'v3';
}

type CoverageGeometry = MultiPolygon | Polygon;

/* Module-level memos so multiple <GatewayLayer /> instances on the same
 * page share one fetch of each file. */
let cachedGateways: RawGateway[] | null = null;
let inFlightGateways: Promise<RawGateway[] | null> | null = null;

let cachedCoverage: CoverageGeometry | null = null;
let inFlightCoverage: Promise<CoverageGeometry | null> | null = null;

async function loadGateways(): Promise<RawGateway[] | null> {
    if (cachedGateways) return cachedGateways;
    if (inFlightGateways) return inFlightGateways;
    inFlightGateways = (async () => {
        try {
            const r = await fetch('/ttnmapper-gateways.json');
            if (!r.ok) return null;
            const body = (await r.json()) as { gateways: RawGateway[] };
            cachedGateways = body.gateways ?? [];
            return cachedGateways;
        } catch {
            return null;
        } finally {
            inFlightGateways = null;
        }
    })();
    return inFlightGateways;
}

async function loadCoverage(): Promise<CoverageGeometry | null> {
    if (cachedCoverage) return cachedCoverage;
    if (inFlightCoverage) return inFlightCoverage;
    inFlightCoverage = (async () => {
        try {
            const r = await fetch('/ttnmapper-coverage.json');
            if (!r.ok) return null;
            const body = (await r.json()) as { coverage: CoverageGeometry };
            cachedCoverage = body.coverage ?? null;
            return cachedCoverage;
        } catch {
            return null;
        } finally {
            inFlightCoverage = null;
        }
    })();
    return inFlightCoverage;
}

export interface GatewayLayerProps {
    /** Stops rendering when false (e.g. tied to a user toggle). */
    visible?: boolean;
}

export default function GatewayLayer({ visible = true }: GatewayLayerProps) {
    const [points, setPoints] = useState<RawGateway[]>([]);
    const [coverage, setCoverage] = useState<CoverageGeometry | null>(null);

    useEffect(() => {
        /* No `firedRef` gate here: React 19's Strict-Mode double-mount in
         * dev would set `fired` on the first mount, run its cleanup
         * (setting `cancelled = true`), and then the second mount would
         * see `fired === true` and skip — but the first mount's promise
         * would never call `setPoints` because it was cancelled. Result:
         * permanent null state. We rely instead on the module-level
         * memos to make the fetches idempotent. */
        let cancelled = false;
        loadGateways().then(gs => {
            if (!cancelled && gs) setPoints(gs);
        });
        loadCoverage().then(cov => {
            if (!cancelled && cov) setCoverage(cov);
        });
        return () => { cancelled = true; };
    }, []);

    const pointsGeoJSON = useMemo(() => {
        if (points.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: points.map(g => ({
                type: 'Feature' as const,
                geometry: {
                    type: 'Point' as const,
                    coordinates: [g.lon, g.lat] as [number, number],
                },
                properties: { net: g.net },
            })),
        };
    }, [points]);

    const coverageGeoJSON = useMemo<Feature<CoverageGeometry> | null>(() => {
        if (!coverage) return null;
        return {
            type: 'Feature',
            geometry: coverage,
            properties: {},
        };
    }, [coverage]);

    if (!visible) return null;

    return (
        <>
            {/* Coverage union — single fill + outline. Renders first so
              * the firefly dots sit on top. */}
            {coverageGeoJSON && (
                <Source id="tm-coverage" type="geojson" data={coverageGeoJSON}>
                    <Layer
                        id="tm-coverage-fill"
                        type="fill"
                        paint={{
                            'fill-color': '#5eead4',
                            'fill-opacity': 0.05,
                        }}
                    />
                    <Layer
                        id="tm-coverage-outline"
                        type="line"
                        paint={{
                            'line-color': 'rgba(94, 234, 212, 0.28)',
                            'line-width': 0.6,
                        }}
                    />
                </Source>
            )}

            {pointsGeoJSON && (
                <Source id="tm-gateways" type="geojson" data={pointsGeoJSON}>
                    {/* Firefly outer halo. */}
                    <Layer
                        id="tm-gateways-halo"
                        type="circle"
                        paint={{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                3, 3,
                                6, 4.5,
                                10, 8,
                                14, 13,
                            ],
                            'circle-color': [
                                'match', ['get', 'net'],
                                'v3', '#5eead4',
                                'v2', '#94a3b8',
                                '#94a3b8',
                            ],
                            'circle-opacity': 0.08,
                            'circle-blur': 0.9,
                        }}
                    />
                    {/* Firefly mid glow. */}
                    <Layer
                        id="tm-gateways-glow"
                        type="circle"
                        paint={{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                3, 1.4,
                                6, 2.2,
                                10, 3.6,
                                14, 6,
                            ],
                            'circle-color': [
                                'match', ['get', 'net'],
                                'v3', '#5eead4',
                                'v2', '#94a3b8',
                                '#94a3b8',
                            ],
                            'circle-opacity': 0.18,
                            'circle-blur': 0.4,
                        }}
                    />
                    {/* Crisp core — pale teal v3 / pale gray v2. */}
                    <Layer
                        id="tm-gateways-core"
                        type="circle"
                        paint={{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                3, 0.5,
                                6, 0.8,
                                10, 1.4,
                                14, 2.4,
                            ],
                            'circle-color': [
                                'match', ['get', 'net'],
                                'v3', '#ccfbf1',
                                'v2', '#cbd5e1',
                                '#cbd5e1',
                            ],
                            'circle-opacity': 0.5,
                        }}
                    />
                </Source>
            )}
        </>
    );
}
