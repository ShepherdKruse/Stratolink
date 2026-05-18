'use client';

import { useEffect, useRef } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { FlightSample } from '@/lib/flights/types';
import { FLIGHT_REPORT_MAP_STYLE } from '@/lib/flights/flightReportMapStyle';

type FlightReportMapProps = {
    flight: FlightSample[];
    freezeMin: number;
    resumeMin: number;
};

export default function FlightReportMap({ flight, freezeMin, resumeMin }: FlightReportMapProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<mapboxgl.Map | null>(null);

    useEffect(() => {
        const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
        const container = containerRef.current;
        if (!container) return;

        if (!token) {
            container.innerHTML =
                '<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#f7f8f9;color:#7a8599;font-size:13px;flex-direction:column;gap:8px">' +
                '<div style="font-weight:600;color:#3d4d6a">Map unavailable</div>' +
                '<div>Set NEXT_PUBLIC_MAPBOX_TOKEN</div></div>';
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

        const allUniqueCoords = uniqueTrack.map((d) => [d.lon!, d.lat!] as [number, number]);
        const lons = allUniqueCoords.map((c) => c[0]);
        const lats = allUniqueCoords.map((c) => c[1]);
        const bounds: mapboxgl.LngLatBoundsLike = [
            [Math.min(...lons) - 0.5, Math.min(...lats) - 0.4],
            [Math.max(...lons) + 0.5, Math.max(...lats) + 0.4],
        ];

        const map = new mapboxgl.Map({
            container,
            style: FLIGHT_REPORT_MAP_STYLE,
            bounds,
            fitBoundsOptions: { padding: 36 },
            attributionControl: false,
            projection: 'mercator',
        });
        mapRef.current = map;

        map.addControl(new mapboxgl.AttributionControl({ compact: true }));
        map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');

        map.on('load', () => {
            map.addSource('ascent', {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    geometry: { type: 'LineString', coordinates: ascentCoords },
                    properties: {},
                },
            });
            map.addLayer({
                id: 'ascent-halo',
                type: 'line',
                source: 'ascent',
                paint: {
                    'line-color': '#c9521f',
                    'line-width': 7,
                    'line-opacity': 0.1,
                    'line-cap': 'round',
                    'line-join': 'round',
                },
            });
            map.addLayer({
                id: 'ascent-line',
                type: 'line',
                source: 'ascent',
                paint: {
                    'line-color': '#c9521f',
                    'line-width': 3,
                    'line-opacity': 0.88,
                    'line-cap': 'round',
                    'line-join': 'round',
                },
            });

            if (resumeCoords.length > 1) {
                map.addSource('resume', {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        geometry: { type: 'LineString', coordinates: resumeCoords },
                        properties: {},
                    },
                });
                map.addLayer({
                    id: 'resume-line',
                    type: 'line',
                    source: 'resume',
                    paint: {
                        'line-color': '#c9521f',
                        'line-width': 2.5,
                        'line-opacity': 0.55,
                        'line-dasharray': [2, 3],
                        'line-cap': 'round',
                    },
                });

                const gpsUpdates = [
                    { lng: -119.002, lat: 33.544, utc: '22:56 UTC', alt: '9,744 m', note: 'GPS resumed' },
                    { lng: -118.391, lat: 32.872, utc: '00:29 UTC', alt: '9,621 m', note: null },
                    { lng: -117.859, lat: 32.219, utc: '01:46 UTC', alt: '9,648 m', note: null },
                    { lng: -117.722, lat: 32.013, utc: '02:03 UTC', alt: '9,682 m', note: 'last fix' },
                ];

                for (const { lng, lat, utc, alt, note } of gpsUpdates) {
                    const el = document.createElement('div');
                    el.style.cssText =
                        'display:flex;flex-direction:column;align-items:center;pointer-events:none;';
                    el.innerHTML =
                        '<div style="' +
                        'background:rgba(255,255,255,.97);' +
                        'border:1px solid rgba(80,101,184,.28);' +
                        'border-radius:4px;' +
                        'padding:3px 8px;' +
                        "font-family:'IBM Plex Mono',monospace;" +
                        'font-size:9.5px;' +
                        'color:#3d4d6a;' +
                        'white-space:nowrap;' +
                        'box-shadow:0 1px 5px rgba(0,0,0,.1);' +
                        'line-height:1.55;' +
                        'text-align:center;' +
                        '">' +
                        utc +
                        '<br>' +
                        alt +
                        (note
                            ? '<br><span style="color:#7a8599;font-size:8.5px">' + note + '</span>'
                            : '') +
                        '</div>' +
                        '<div style="width:1.5px;height:7px;background:rgba(80,101,184,.35);"></div>' +
                        '<div style="width:8px;height:8px;border-radius:50%;background:#5065b8;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.22);"></div>';
                    new mapboxgl.Marker({ element: el, anchor: 'bottom' })
                        .setLngLat([lng, lat])
                        .addTo(map);
                }
            }

            map.addSource('drift', {
                type: 'geojson',
                data: {
                    type: 'Feature',
                    geometry: {
                        type: 'LineString',
                        coordinates: [
                            [-121.572, 36.616],
                            [-119.002, 33.544],
                        ],
                    },
                    properties: {},
                },
            });
            map.addLayer({
                id: 'drift-line',
                type: 'line',
                source: 'drift',
                paint: {
                    'line-color': '#a0aab8',
                    'line-width': 1.5,
                    'line-opacity': 0.5,
                    'line-dasharray': [4, 6],
                    'line-cap': 'round',
                },
            });

            const mkMarker = (
                lngLat: [number, number],
                color: string,
                size: number,
                html: string,
            ) => {
                const el = document.createElement('div');
                el.style.cssText = [
                    'width:' + size + 'px',
                    'height:' + size + 'px',
                    'border-radius:50%',
                    'background:' + color,
                    'border:2.5px solid white',
                    'box-shadow:0 1px 5px rgba(0,0,0,.3)',
                    'cursor:pointer',
                ].join(';');
                new mapboxgl.Marker({ element: el })
                    .setLngLat(lngLat)
                    .setPopup(
                        new mapboxgl.Popup({ offset: 12, closeButton: false }).setHTML(html),
                    )
                    .addTo(map);
            };

            mkMarker(
                [-122.426, 37.728],
                '#2d8c55',
                13,
                '<div class="popup-title">Launch Site</div>' +
                    '<div class="popup-detail">37.728°N, 122.426°W<br>T+0 · 734 m · 15:55 UTC</div>',
            );

            mkMarker(
                [-121.572, 36.616],
                '#c9521f',
                11,
                '<div class="popup-title">GPS Freeze Point</div>' +
                    '<div class="popup-detail">36.616°N, 121.572°W<br>T+145 min · GPS locked at 6,924 m<br>Pressure: 409 hPa → ~7,022 m actual</div>',
            );
        });

        return () => {
            map.remove();
            mapRef.current = null;
        };
    }, [flight, freezeMin, resumeMin]);

    return <div ref={containerRef} id="flightmap" className="flight-report-map" />;
}
