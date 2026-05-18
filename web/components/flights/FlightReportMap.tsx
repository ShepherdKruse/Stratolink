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

function addRouteLine(
    map: mapboxgl.Map,
    sourceId: string,
    coords: [number, number][],
    opts: {
        color: string;
        width: number;
        opacity: number;
        dash?: number[];
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

    const haloWidth = opts.haloWidth ?? opts.width + 5;
    map.addLayer({
        id: `${sourceId}-halo`,
        type: 'line',
        source: sourceId,
        paint: {
            'line-color': opts.haloColor ?? '#ffffff',
            'line-width': haloWidth,
            'line-opacity': 0.92,
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

function createCalloutMarker(utc: string, alt: string, note: string | null) {
    const el = document.createElement('div');
    el.className = 'flight-map-callout';
    const label = document.createElement('div');
    label.className = 'flight-map-callout-label';
    label.innerHTML = `<strong>${utc}</strong><br>${alt}`;
    if (note) {
        const noteEl = document.createElement('span');
        noteEl.className = 'flight-map-callout-note';
        noteEl.textContent = note;
        label.appendChild(document.createElement('br'));
        label.appendChild(noteEl);
    }
    const stem = document.createElement('div');
    stem.className = 'flight-map-callout-stem';
    const dot = document.createElement('div');
    dot.className = 'flight-map-callout-dot';
    el.append(label, stem, dot);
    return el;
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

        const driftCoords: [number, number][] = [
            [-121.572, 36.616],
            [-119.002, 33.544],
        ];

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
            fitBoundsOptions: { padding: 48 },
            attributionControl: false,
            projection: 'mercator',
        });
        mapRef.current = map;

        map.addControl(new mapboxgl.AttributionControl({ compact: true }));
        map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');

        map.on('load', () => {
            addRouteLine(map, 'drift', driftCoords, {
                color: '#3d4d6a',
                width: 3.5,
                opacity: 0.92,
                dash: [2, 1.5],
                haloColor: '#eef0f2',
                haloWidth: 9,
            });

            addRouteLine(map, 'ascent', ascentCoords, {
                color: '#c9521f',
                width: 3.5,
                opacity: 0.95,
                haloColor: '#ffffff',
                haloWidth: 8,
            });

            if (resumeCoords.length > 1) {
                addRouteLine(map, 'resume', resumeCoords, {
                    color: '#a8481a',
                    width: 3,
                    opacity: 0.9,
                    dash: [1.5, 1.2],
                    haloColor: '#ffffff',
                    haloWidth: 7,
                });

                const gpsUpdates = [
                    { lng: -119.002, lat: 33.544, utc: '22:56 UTC', alt: '9,744 m', note: 'GPS resumed' },
                    { lng: -118.391, lat: 32.872, utc: '00:29 UTC', alt: '9,621 m', note: null },
                    { lng: -117.859, lat: 32.219, utc: '01:46 UTC', alt: '9,648 m', note: null },
                    { lng: -117.722, lat: 32.013, utc: '02:03 UTC', alt: '9,682 m', note: 'last fix' },
                ];

                for (const { lng, lat, utc, alt, note } of gpsUpdates) {
                    new mapboxgl.Marker({
                        element: createCalloutMarker(utc, alt, note),
                        anchor: 'bottom',
                    })
                        .setLngLat([lng, lat])
                        .addTo(map);
                }
            }

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
                    'box-shadow:0 2px 6px rgba(27,36,56,.35)',
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
                14,
                '<div class="popup-title">Launch Site</div>' +
                    '<div class="popup-detail">37.728°N, 122.426°W<br>T+0 · 734 m · 15:55 UTC</div>',
            );

            mkMarker(
                [-121.572, 36.616],
                '#c9521f',
                12,
                '<div class="popup-title">GPS Freeze Point</div>' +
                    '<div class="popup-detail">36.616°N, 121.572°W<br>T+145 min · GPS locked at 6,924 m<br>Pressure: 409 hPa → ~7,022 m actual</div>',
            );
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
