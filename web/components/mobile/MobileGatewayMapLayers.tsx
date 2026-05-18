'use client';

import { useMemo } from 'react';
import { Layer, Source } from 'react-map-gl/mapbox';
import type { GatewayReception } from '../dashboard-v2/atoms';
import { isUsableGpsCoordinate } from '@/lib/mapGeo';
import { buildGatewaysGeoJSON, buildReceptionLinesGeoJSON, gatewaysWithLocation } from './mobileGatewayGeo';

interface MobileGatewayMapLayersProps {
    /** Prefix for layer/source ids so multiple maps on one page never clash. */
    idPrefix: string;
    gateways: GatewayReception[] | null | undefined;
    balloonLat: number | null;
    balloonLon: number | null;
    styleLoaded: boolean;
}

/** Orange gateway pins + faint reception lines on a Mapbox map.
 *  Matches the desktop V2MissionMap treatment — pins on the real map,
 *  not a separate polar plot. */
export default function MobileGatewayMapLayers({
    idPrefix,
    gateways,
    balloonLat,
    balloonLon,
    styleLoaded,
}: MobileGatewayMapLayersProps) {
    const located = useMemo(() => gatewaysWithLocation(gateways), [gateways]);

    const balloonOk =
        balloonLat != null &&
        balloonLon != null &&
        isUsableGpsCoordinate(balloonLat, balloonLon);

    const gatewaysGeoJSON = useMemo(
        () => (located.length ? buildGatewaysGeoJSON(located) : null),
        [located],
    );

    const receptionLinesGeoJSON = useMemo(() => {
        if (!balloonOk || !located.length) return null;
        return buildReceptionLinesGeoJSON(balloonLat, balloonLon, located);
    }, [balloonOk, balloonLat, balloonLon, located]);

    if (!styleLoaded || !located.length) return null;

    return (
        <>
            {balloonOk && receptionLinesGeoJSON ? (
                <Source id={`${idPrefix}-reception-lines`} type="geojson" data={receptionLinesGeoJSON}>
                    <Layer
                        id={`${idPrefix}-reception-line`}
                        type="line"
                        paint={{
                            'line-color': [
                                'interpolate',
                                ['linear'],
                                ['get', 'rssi'],
                                -130,
                                'rgba(245, 158, 11, 0.2)',
                                -100,
                                'rgba(245, 158, 11, 0.45)',
                                -85,
                                'rgba(251, 191, 36, 0.65)',
                            ],
                            'line-width': [
                                'interpolate',
                                ['linear'],
                                ['get', 'rssi'],
                                -130,
                                0.8,
                                -85,
                                1.8,
                            ],
                        }}
                    />
                </Source>
            ) : null}

            {gatewaysGeoJSON ? (
                <Source id={`${idPrefix}-gateways`} type="geojson" data={gatewaysGeoJSON}>
                    <Layer
                        id={`${idPrefix}-gateway-pin`}
                        type="circle"
                        paint={{
                            'circle-color': '#f59e0b',
                            'circle-radius': 6,
                            'circle-stroke-width': 1.5,
                            'circle-stroke-color': '#fbbf24',
                            'circle-stroke-opacity': 0.95,
                            'circle-opacity': 0.92,
                        }}
                    />
                </Source>
            ) : null}
        </>
    );
}
