/**
 * Balloon-centered spreading-factor range rings.
 *
 * Replaces the hemisphere-wide coverage field with a local view answering
 * "should we be getting signal right now?". Draws three geodesic rings
 * around the balloon — SF7 (solid, bright, the range we fly), SF10 and SF12
 * (dashed, fainter, theoretical reach if the spreading factor were lowered),
 * each capped at the altitude-limited radio horizon — plus nearby gateways
 * (lit when inside SF7 range) and a dashed connector to the nearest one.
 *
 * Drop inside a react-map-gl `<Map>`. Self-loads the gateway points.
 */
'use client';

import { useMemo } from 'react';
import { Layer, Source } from 'react-map-gl/mapbox';
import type { Feature, LineString } from 'geojson';
import { useGatewayPoints } from '@/lib/gateways/data';
import { geodesicCircle, nearestGateway, ringKm, type RingSf } from '@/lib/gateways/range';

interface RingSpec {
    sf: RingSf;
    color: string;
    fill: number;
    line: number;
    dash: number[] | null;
}

/* Outermost first so SF7 draws on top. */
const RINGS: RingSpec[] = [
    { sf: 'sf12', color: '#3fb8a0', fill: 0.04, line: 0.3, dash: [2, 3] },
    { sf: 'sf10', color: '#4fc8b4', fill: 0.05, line: 0.42, dash: [4, 3] },
    { sf: 'sf7', color: '#6fe0c8', fill: 0.07, line: 0.85, dash: null },
];

export interface GatewayRangeRingsProps {
    lat: number;
    lon: number;
    altM: number | null;
}

export default function GatewayRangeRings({ lat, lon, altM }: GatewayRangeRingsProps) {
    const points = useGatewayPoints();

    const sf7Km = ringKm('sf7', altM);
    const sf12Km = ringKm('sf12', altM);

    /* Ring polygons. */
    const ringPolys = useMemo(
        () =>
            RINGS.map((r) => ({
                spec: r,
                poly: geodesicCircle(lon, lat, ringKm(r.sf, altM)),
            })),
        [lat, lon, altM],
    );

    const nearest = useMemo(() => nearestGateway(lat, lon, points), [lat, lon, points]);

    const nearestLine = useMemo<Feature<LineString> | null>(() => {
        if (!nearest) return null;
        return {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: [[lon, lat], [nearest.lon, nearest.lat]] },
            properties: {},
        };
    }, [nearest, lat, lon]);

    /* Nearby gateway points only — keeps the local view uncluttered and the
     * GeoJSON small as the balloon scrubs. Cap the radius when altitude (and
     * thus the SF12 ring) is unknown so we never render all ~14k points. */
    const pointsGeoJSON = useMemo(() => {
        const reach = Number.isFinite(sf12Km) ? sf12Km : 600;
        const radiusKm = Math.max(reach * 1.6, 120);
        const features = [];
        for (const g of points) {
            /* cheap bounding pre-filter before the haversine */
            const dLat = Math.abs(g.lat - lat);
            if (dLat > radiusKm / 100) continue;
            const dist =
                6371 *
                2 *
                Math.asin(
                    Math.sqrt(
                        Math.sin((((g.lat - lat) * Math.PI) / 180) / 2) ** 2 +
                            Math.cos((lat * Math.PI) / 180) *
                                Math.cos((g.lat * Math.PI) / 180) *
                                Math.sin((((g.lon - lon) * Math.PI) / 180) / 2) ** 2,
                    ),
                );
            if (dist > radiusKm) continue;
            features.push({
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: [g.lon, g.lat] as [number, number] },
                properties: { inRange: dist <= sf7Km ? 1 : 0 },
            });
        }
        return { type: 'FeatureCollection' as const, features };
    }, [points, lat, lon, sf7Km, sf12Km]);

    return (
        <>
            {/* Ring fills (outermost → innermost). */}
            {ringPolys.map(({ spec, poly }) => (
                <Source key={`rr-${spec.sf}-f`} id={`rr-ring-${spec.sf}-src`} type="geojson" data={poly}>
                    <Layer
                        id={`rr-ring-${spec.sf}-fill`}
                        type="fill"
                        paint={{ 'fill-color': spec.color, 'fill-opacity': spec.fill, 'fill-antialias': false }}
                    />
                    <Layer
                        id={`rr-ring-${spec.sf}-line`}
                        type="line"
                        paint={{
                            'line-color': spec.color,
                            'line-width': spec.sf === 'sf7' ? 2 : 1.2,
                            'line-opacity': spec.line,
                            ...(spec.dash ? { 'line-dasharray': spec.dash } : {}),
                        }}
                    />
                </Source>
            ))}

            {/* Nearby gateways — lit when inside SF7 range, dim otherwise. */}
            <Source id="rr-gateways-src" type="geojson" data={pointsGeoJSON}>
                <Layer
                    id="rr-gateways"
                    type="circle"
                    paint={{
                        'circle-radius': 3.5,
                        'circle-color': ['case', ['==', ['get', 'inRange'], 1], '#6fe0c8', '#4a6b66'],
                        'circle-stroke-color': 'rgba(95,212,188,0.5)',
                        'circle-stroke-width': 1,
                        'circle-opacity': 0.9,
                    }}
                />
            </Source>

            {/* Dashed connector to the nearest gateway. */}
            {nearestLine && (
                <Source id="rr-nearest-src" type="geojson" data={nearestLine}>
                    <Layer
                        id="rr-nearest-line"
                        type="line"
                        paint={{
                            'line-color': '#e0e6f0',
                            'line-width': 1,
                            'line-dasharray': [2, 2],
                            'line-opacity': 0.5,
                        }}
                    />
                </Source>
            )}
        </>
    );
}
