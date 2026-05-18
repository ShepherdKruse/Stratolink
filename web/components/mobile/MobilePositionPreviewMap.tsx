'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Source } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import mapboxgl from 'mapbox-gl';

import { isUsableGpsCoordinate, isWebGLAvailable } from '@/lib/mapGeo';
import type { GatewayReception } from '../dashboard-v2/atoms';
import SlMapMini from './SlMapMini';
import MobileGatewayMapLayers from './MobileGatewayMapLayers';
import { gatewaysWithLocation } from './mobileGatewayGeo';

const MAP_STYLE_DARK = 'mapbox://styles/mapbox/dark-v11';

interface FlightPathPoint {
    lat: number;
    lon: number;
}

interface MobilePositionPreviewMapProps {
    lat: number;
    lon: number;
    flightPathData?: FlightPathPoint[];
    /** TTN rx_metadata gateways for the latest uplink — rendered as orange pins. */
    gateways?: GatewayReception[] | null;
}

function buildLngLatBounds(coords: ReadonlyArray<readonly [number, number]>): mapboxgl.LngLatBounds | null {
    if (!coords.length) return null;
    const first = coords[0] as mapboxgl.LngLatLike;
    const b = new mapboxgl.LngLatBounds(first, first);
    for (let i = 1; i < coords.length; i++) {
        b.extend(coords[i] as mapboxgl.LngLatLike);
    }
    return b;
}

export default function MobilePositionPreviewMap({
    lat,
    lon,
    flightPathData = [],
    gateways = null,
}: MobilePositionPreviewMapProps) {
    const mapRef = useRef<MapRef>(null);
    const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);

    useEffect(() => {
        setWebglOk(isWebGLAvailable());
    }, []);

    const handleStyleLoad = useCallback(() => setStyleLoaded(true), []);

    const pathCoords = useMemo(
        () =>
            flightPathData
                .filter((p) => isUsableGpsCoordinate(p.lat, p.lon))
                .map((p) => [p.lon, p.lat] as [number, number]),
        [flightPathData],
    );

    const markerOk = isUsableGpsCoordinate(lat, lon);
    const locatedGateways = useMemo(() => gatewaysWithLocation(gateways), [gateways]);
    const gatewayCount = locatedGateways.length;

    const markerGeoJSON = useMemo(() => {
        if (!markerOk)
            return { type: 'FeatureCollection' as const, features: [] as GeoJSON.Feature[] };
        return {
            type: 'FeatureCollection' as const,
            features: [
                {
                    type: 'Feature' as const,
                    geometry: { type: 'Point' as const, coordinates: [lon, lat] },
                    properties: {},
                },
            ],
        } satisfies GeoJSON.FeatureCollection;
    }, [lat, lon, markerOk]);

    const lineGeoJSON = useMemo(() => {
        if (pathCoords.length < 2) {
            return { type: 'FeatureCollection' as const, features: [] as GeoJSON.Feature[] };
        }
        return {
            type: 'FeatureCollection' as const,
            features: [
                {
                    type: 'Feature' as const,
                    geometry: { type: 'LineString' as const, coordinates: pathCoords },
                    properties: {},
                },
            ],
        } satisfies GeoJSON.FeatureCollection;
    }, [pathCoords]);

    useEffect(() => {
        if (!styleLoaded || !mapRef.current || !webglOk) return;
        const map = mapRef.current.getMap();
        if (!map?.loaded?.()) return;

        const allPts: [number, number][] = [...pathCoords];
        if (markerOk) allPts.push([lon, lat]);
        for (const g of locatedGateways) {
            if (g.lat != null && g.lon != null) allPts.push([g.lon, g.lat]);
        }

        const bounds = allPts.length ? buildLngLatBounds(allPts) : null;

        try {
            if (bounds && !bounds.isEmpty() && pathCoords.length >= 2) {
                map.fitBounds(bounds, { padding: 20, maxZoom: 14, duration: 500 });
            } else if (markerOk) {
                map.flyTo({ center: [lon, lat], zoom: 11, duration: 500 });
            } else {
                map.jumpTo({ center: [-98, 39], zoom: 3 });
            }
        } catch {
            /* ignore */
        }
    }, [styleLoaded, webglOk, lat, lon, markerOk, pathCoords, locatedGateways]);

    if (!mapboxToken) {
        return (
            <div className="relative h-[220px] w-full overflow-hidden bg-[var(--bg-1)]">
                <SlMapMini />
            </div>
        );
    }

    if (webglOk === false) {
        return (
            <div className="relative h-[220px] w-full overflow-hidden bg-[var(--bg-1)]">
                <SlMapMini />
            </div>
        );
    }

    return (
        <div className="pointer-events-none relative h-[220px] w-full select-none bg-[#0d0d0d] [&_.mapboxgl-ctrl-attrib-inner]:opacity-70">
            <Map
                ref={mapRef}
                mapboxAccessToken={mapboxToken}
                initialViewState={{
                    longitude: markerOk ? lon : -98,
                    latitude: markerOk ? lat : 39,
                    zoom: markerOk ? 11 : 3,
                }}
                dragPan={false}
                dragRotate={false}
                scrollZoom={false}
                boxZoom={false}
                keyboard={false}
                doubleClickZoom={false}
                touchZoomRotate={false}
                style={{ width: '100%', height: '100%' }}
                mapStyle={MAP_STYLE_DARK}
                projection="mercator"
                onLoad={handleStyleLoad}>
                <MobileGatewayMapLayers
                    idPrefix="pos"
                    gateways={gateways}
                    balloonLat={markerOk ? lat : null}
                    balloonLon={markerOk ? lon : null}
                    styleLoaded={styleLoaded}
                />
                {styleLoaded && lineGeoJSON.features.length > 0 ? (
                    <Source id="position-preview-path" type="geojson" data={lineGeoJSON}>
                        <Layer
                            id="position-preview-path-line"
                            type="line"
                            paint={{
                                'line-color': '#4a90d9',
                                'line-width': 4,
                                'line-opacity': 0.82,
                            }}
                            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                        />
                    </Source>
                ) : null}
                {styleLoaded && markerGeoJSON.features.length > 0 ? (
                    <Source id="position-preview-marker" type="geojson" data={markerGeoJSON}>
                        <Layer
                            id="position-preview-dot"
                            type="circle"
                            paint={{
                                'circle-color': '#44aa99',
                                'circle-radius': 11,
                                'circle-opacity': 0.95,
                                'circle-stroke-width': 3,
                                'circle-stroke-color': '#66ccbb',
                                'circle-stroke-opacity': 0.9,
                            }}
                        />
                    </Source>
                ) : null}
            </Map>
            {gatewayCount > 0 ? (
                <div
                    className="absolute right-3 top-3 font-mono text-[10px] uppercase tracking-[0.08em]"
                    style={{
                        padding: '4px 8px',
                        background: 'rgba(11, 14, 19, 0.82)',
                        border: '1px solid rgba(245, 158, 11, 0.45)',
                        color: '#fbbf24',
                        backdropFilter: 'blur(12px)',
                    }}>
                    {gatewayCount} GW
                </div>
            ) : null}
        </div>
    );
}
