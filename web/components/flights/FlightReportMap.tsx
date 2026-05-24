'use client';

import { useEffect, useRef } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { addGatewayLayersToMap } from '@/components/maps/addGatewayLayersToMap';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';
import type { FlightSample } from '@/lib/flights/types';
import { FLIGHT_REPORT_MAP_STYLE } from '@/lib/flights/flightReportMapStyle';
import type { FlightMapAnnotation } from '@/lib/flights/flightMapAnnotations';
import {
    BAJA_RUN_FREEZE_ANNOTATION,
    BAJA_RUN_GPS_ANNOTATIONS,
    BAJA_RUN_LAUNCH_ANNOTATION,
} from '@/lib/flights/flightMapAnnotations';

type FlightReportMapProps = {
    flight: FlightSample[];
    freezeMin: number;
    resumeMin: number;
};

function addRouteLine(
    map: mapboxgl.Map,
    sourceId: string,
    coords: [number, number][],
    opts: {
        color: string;
        width: number;
        opacity: number;
        dash?: number[];
        glowColor?: string;
        glowWidth?: number;
        haloColor?: string;
        haloWidth?: number;
    },
) {
    map.addSource(sourceId, {
        type: 'geojson',
        data: {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: coords },
            properties: {},
        },
    });

    if (opts.glowColor) {
        map.addLayer({
            id: `${sourceId}-glow`,
            type: 'line',
            source: sourceId,
            paint: {
                'line-color': opts.glowColor,
                'line-width': opts.glowWidth ?? 14,
                'line-opacity': 0.38,
                'line-blur': 2,
                'line-cap': 'round',
                'line-join': 'round',
            },
        });
    }

    const haloWidth = opts.haloWidth ?? opts.width + 5;
    map.addLayer({
        id: `${sourceId}-halo`,
        type: 'line',
        source: sourceId,
        paint: {
            'line-color': opts.haloColor ?? '#ffffff',
            'line-width': haloWidth,
            'line-opacity': 0.95,
            'line-cap': 'round',
            'line-join': 'round',
        },
    });

    map.addLayer({
        id: `${sourceId}-line`,
        type: 'line',
        source: sourceId,
        paint: {
            'line-color': opts.color,
            'line-width': opts.width,
            'line-opacity': opts.opacity,
            'line-cap': 'round',
            'line-join': 'round',
            ...(opts.dash ? { 'line-dasharray': opts.dash } : {}),
        },
    });
}

function createAnnotationLabel(a: FlightMapAnnotation) {
    const el = document.createElement('div');
    el.className = 'flight-map-annotation';
    const pill = document.createElement('div');
    pill.className = 'flight-map-annotation-pill';
    pill.innerHTML =
        `<span class="flight-map-annotation-time">${a.utc}</span>` +
        `<span class="flight-map-annotation-alt">${a.alt}</span>` +
        (a.note ? `<span class="flight-map-annotation-note">${a.note}</span>` : '');
    el.appendChild(pill);
    return el;
}

function addMapAnnotations(map: mapboxgl.Map, annotations: FlightMapAnnotation[]) {
    const leaderFeatures = annotations.map((a) => ({
        type: 'Feature' as const,
        geometry: {
            type: 'LineString' as const,
            coordinates: [a.label, a.point],
        },
        properties: {},
    }));

    const pointFeatures = annotations.map((a) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: a.point },
        properties: { color: a.dotColor ?? '#5065b8' },
    }));

    map.addSource('annotation-leaders', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: leaderFeatures },
    });
    map.addLayer({
        id: 'annotation-leaders',
        type: 'line',
        source: 'annotation-leaders',
        paint: {
            'line-color': '#b4bccc',
            'line-width': 1,
            'line-opacity': 0.9,
        },
    });

    map.addSource('annotation-points', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: pointFeatures },
    });
    map.addLayer({
        id: 'annotation-points-outer',
        type: 'circle',
        source: 'annotation-points',
        paint: {
            'circle-radius': 7,
            'circle-color': '#ffffff',
            'circle-opacity': 1,
        },
    });
    map.addLayer({
        id: 'annotation-points',
        type: 'circle',
        source: 'annotation-points',
        paint: {
            'circle-radius': 4.5,
            'circle-color': ['get', 'color'],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
        },
    });

    for (const a of annotations) {
        new mapboxgl.Marker({ element: createAnnotationLabel(a), anchor: 'center' })
            .setLngLat(a.label)
            .addTo(map);
    }
}

export default function FlightReportMap({ flight, freezeMin, resumeMin }: FlightReportMapProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<mapboxgl.Map | null>(null);

    useEffect(() => {
        const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
        const container = containerRef.current;
        if (!container) return;

        if (!token) {
            container.innerHTML =
                '<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#eef0f2;color:#7a8599;font-size:13px;flex-direction:column;gap:8px">' +
                '<div style="font-weight:600;color:#3d4d6a">Map unavailable</div>' +
                '<div>Set NEXT_PUBLIC_MAPBOX_TOKEN</div></div>'.replaceAll(
                    'motion.',
                    '',
                );
            return;
        }

        mapboxgl.accessToken = token;

        const allTrack = flight.filter((d) => d.lat != null && d.lon != null);
        const seen = new Set<string>();
        const uniqueTrack = allTrack.filter((d) => {
            const key = d.lat!.toFixed(3) + ',' + d.lon!.toFixed(3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });

        const ascentCoords = allTrack
            .filter((d) => d.mins <= freezeMin)
            .map((d) => [d.lon!, d.lat!] as [number, number]);

        const resumeCoords = uniqueTrack
            .filter((d) => d.mins >= resumeMin)
            .map((d) => [d.lon!, d.lat!] as [number, number]);

        const driftCoords: [number, number][] = [
            [-121.572, 36.616],
            [-119.002, 33.544],
        ];

        const allUniqueCoords = uniqueTrack.map((d) => [d.lon!, d.lat!] as [number, number]);
        const lons = allUniqueCoords.map((c) => c[0]);
        const lats = allUniqueCoords.map((c) => c[1]);
        const bounds: mapboxgl.LngLatBoundsLike = [
            [Math.min(...lons) - 0.85, Math.min(...lats) - 0.45],
            [Math.max(...lons) + 0.35, Math.max(...lats) + 0.4],
        ];

        const map = new mapboxgl.Map({
            container,
            style: FLIGHT_REPORT_MAP_STYLE,
            bounds,
            fitBoundsOptions: { padding: { top: 36, bottom: 36, left: 24, right: 56 } },
            attributionControl: false,
            projection: 'globe',
        });
        mapRef.current = map;

        map.addControl(new mapboxgl.AttributionControl({ compact: true }));
        map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');

        map.on('load', () => {
            quietBasemapLabels(map);
            /* Static TTN ground-station coverage — added first so the
             * route lines + markers render on top. */
            void addGatewayLayersToMap(map);

            addRouteLine(map, 'drift', driftCoords, {
                color: '#3d4d6a',
                width: 2.5,
                opacity: 0.88,
                dash: [2, 1.5],
                haloColor: '#eef0f2',
                haloWidth: 7,
            });

            addRouteLine(map, 'ascent', ascentCoords, {
                color: '#c9521f',
                width: 3.5,
                opacity: 0.96,
                glowColor: 'rgba(201, 82, 31, 0.45)',
                glowWidth: 16,
                haloColor: '#ffffff',
                haloWidth: 8,
            });

            if (resumeCoords.length > 1) {
                addRouteLine(map, 'resume', resumeCoords, {
                    color: '#a8481a',
                    width: 2.8,
                    opacity: 0.9,
                    dash: [1.5, 1.2],
                    glowColor: 'rgba(201, 82, 31, 0.28)',
                    glowWidth: 12,
                    haloColor: '#ffffff',
                    haloWidth: 6,
                });
            }

            const mapAnnotations: FlightMapAnnotation[] = [
                BAJA_RUN_LAUNCH_ANNOTATION,
                BAJA_RUN_FREEZE_ANNOTATION,
                ...(resumeCoords.length > 1 ? BAJA_RUN_GPS_ANNOTATIONS : []),
            ];
            addMapAnnotations(map, mapAnnotations);
        });

        return () => {
            map.remove();
            mapRef.current = null;
        };
    }, [flight, freezeMin, resumeMin]);

    return (
        <div className="flight-report-map-wrap">
            <div ref={containerRef} className="flight-report-map" />
            <ul className="flight-map-legend" aria-label="Map legend">
                <li>
                    <span className="flight-map-legend-swatch flight-map-legend-swatch--solid" />
                    GPS ascent (confirmed fixes)
                </li>
                <li>
                    <span className="flight-map-legend-swatch flight-map-legend-swatch--drift" />
                    Implied drift while GPS frozen
                </li>
                <li>
                    <span className="flight-map-legend-swatch flight-map-legend-swatch--resume" />
                    Post-resume track (unique positions)
                </li>
            </ul>
        </div>
    );
}
