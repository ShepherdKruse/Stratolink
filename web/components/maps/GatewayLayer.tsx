/**
 * TTN gateway coverage layer.
 *
 * Renders two static snapshots from ttnmapper.org as an additive heat field
 * with crisp points on top (see docs/gateway design spec):
 *
 *   1. `public/ttnmapper-gateways.json` — ~14k gateway points. These drive
 *      a Mapbox `heatmap` layer (additive by nature: overlapping gateways
 *      sum into a brighter teal glow, isolated ones stay faint, no hard
 *      edges) plus a single crisp bright-teal point layer on top so the
 *      gateway *locations* read as data distinct from the coverage wash.
 *
 *   2. `public/ttnmapper-coverage.json` — the **union** of 250 km buffers
 *      around every gateway, one MultiPolygon. Rendered as an edgeless,
 *      very-low-opacity fill underneath the heatmap so true geographic
 *      reach still shows (the heatmap radius is screen-pixels, not km)
 *      without the hard outline that used to quilt the view.
 *
 * The heat field + coverage underlay are inserted beneath the basemap's
 * label layers (so city / country names stay readable); the points sit on
 * top of everything.
 *
 * Both refreshed by `npm run gateways:refresh`. Loads lazily on first
 * mount via module-level memos shared across instances.
 *
 * Usage: drop `<GatewayLayer />` inside a react-map-gl `<Map>`.
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { Layer, Source, useMap } from 'react-map-gl/mapbox';
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
    const { current: mapRef } = useMap();
    /* Id of the basemap's first symbol (label) layer. The coverage wash +
     * heatmap are inserted before it so labels stay readable on top of the
     * glow; undefined falls back to "append on top" (still a valid stack). */
    const [beforeId, setBeforeId] = useState<string | undefined>(undefined);

    useEffect(() => {
        const map = mapRef?.getMap?.();
        if (!map) return;
        const findFirstSymbol = () => {
            try {
                const layers = map.getStyle()?.layers ?? [];
                const sym = layers.find((l) => l.type === 'symbol');
                setBeforeId(sym?.id);
            } catch {
                /* style not ready yet — a later styledata event will retry */
            }
        };
        findFirstSymbol();
        map.on('styledata', findFirstSymbol);
        return () => {
            map.off('styledata', findFirstSymbol);
        };
    }, [mapRef]);

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
            {/* Coverage union — edgeless, very-low-opacity true-km reach.
              * Sits beneath the heatmap (and basemap labels). No outline:
              * the hard edge is what used to quilt the view. */}
            {coverageGeoJSON && (
                <Source id="tm-coverage" type="geojson" data={coverageGeoJSON}>
                    <Layer
                        id="tm-coverage-fill"
                        type="fill"
                        beforeId={beforeId}
                        paint={{
                            'fill-color': '#3fb8a0',
                            'fill-opacity': 0.06,
                            'fill-antialias': false,
                        }}
                    />
                </Source>
            )}

            {pointsGeoJSON && (
                <Source id="tm-gateways" type="geojson" data={pointsGeoJSON}>
                    {/* Additive heat field — overlapping gateways sum into a
                      * brighter teal glow; isolated ones stay faint. Inserted
                      * beneath the labels. */}
                    <Layer
                        id="tm-gateway-coverage"
                        type="heatmap"
                        beforeId={beforeId}
                        paint={{
                            'heatmap-weight': 1,
                            /* Low intensity — keeps ultra-dense regions (Europe
                              * holds most of the ~14k gateways) from clamping the
                              * whole continent to the top of the ramp. */
                            'heatmap-intensity': [
                                'interpolate', ['linear'], ['zoom'],
                                2, 0.25,
                                5, 0.5,
                                10, 0.9,
                            ],
                            /* Gentle ramp topping out at a soft teal (not the
                              * old near-opaque 0.46) so saturated areas glow
                              * rather than paint over the basemap. */
                            'heatmap-color': [
                                'interpolate', ['linear'], ['heatmap-density'],
                                0, 'rgba(63,184,160,0)',
                                0.2, 'rgba(63,184,160,0.08)',
                                0.45, 'rgba(63,184,160,0.16)',
                                0.7, 'rgba(80,200,180,0.24)',
                                1, 'rgba(120,225,205,0.32)',
                            ],
                            /* Tighter kernels = less overlap-summing = more
                              * internal structure instead of one flat blob. */
                            'heatmap-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                2, 10,
                                5, 26,
                                10, 60,
                            ],
                            /* Sub-1 opacity lets the basemap read through even
                              * the densest patches. */
                            'heatmap-opacity': [
                                'interpolate', ['linear'], ['zoom'],
                                2, 0.6,
                                6, 0.85,
                            ],
                        }}
                    />
                    {/* Crisp bright-teal point on top — gateway locations as
                      * data, distinct from the wash. Hidden on the world / globe
                      * view (where 14k dots would just pile onto the glow) and
                      * fading in as you zoom to continental / local scale. */}
                    <Layer
                        id="tm-gateway-points"
                        type="circle"
                        paint={{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 1.6,
                                8, 4,
                            ],
                            'circle-color': '#5fd4bc',
                            'circle-stroke-color': 'rgba(95,212,188,0.5)',
                            'circle-stroke-width': 1,
                            'circle-opacity': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 0,
                                6, 0.85,
                            ],
                        }}
                    />
                </Source>
            )}
        </>
    );
}
