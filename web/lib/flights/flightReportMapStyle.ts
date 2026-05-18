import type { StyleSpecification } from 'mapbox-gl';

/** Muted cartography aligned with flight-report.css (--fr-* tokens). */
export const FLIGHT_REPORT_MAP_STYLE: StyleSpecification = {
    version: 8,
    name: 'Stratolink Flight Report',
    sources: {
        'mapbox-streets': {
            type: 'vector',
            url: 'mapbox://mapbox.mapbox-streets-v8',
        },
    },
    glyphs: 'mapbox://fonts/mapbox/{fontstack}/{range}.pbf',
    layers: [
        {
            id: 'background',
            type: 'background',
            paint: { 'background-color': '#eef0f2' },
        },
        {
            id: 'landcover',
            type: 'fill',
            source: 'mapbox-streets',
            'source-layer': 'landcover',
            paint: {
                'fill-color': '#e4e7ec',
                'fill-opacity': 0.55,
            },
        },
        {
            id: 'landuse',
            type: 'fill',
            source: 'mapbox-streets',
            'source-layer': 'landuse',
            paint: {
                'fill-color': '#e0e4e9',
                'fill-opacity': 0.35,
            },
        },
        {
            id: 'water',
            type: 'fill',
            source: 'mapbox-streets',
            'source-layer': 'water',
            paint: { 'fill-color': '#b6c9e2' },
        },
        {
            id: 'waterway',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'waterway',
            paint: {
                'line-color': '#a3b8d4',
                'line-width': 0.8,
                'line-opacity': 0.85,
            },
        },
        {
            id: 'road-major',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'road',
            filter: [
                'in',
                ['get', 'class'],
                ['literal', ['motorway', 'trunk', 'primary']],
            ],
            paint: {
                'line-color': '#cdd2da',
                'line-width': [
                    'interpolate',
                    ['linear'],
                    ['zoom'],
                    4,
                    0.3,
                    8,
                    1.2,
                    12,
                    2.5,
                ],
                'line-opacity': 0.7,
            },
        },
        {
            id: 'road-minor',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'road',
            filter: [
                'in',
                ['get', 'class'],
                ['literal', ['secondary', 'tertiary', 'street', 'street_limited']],
            ],
            paint: {
                'line-color': '#d8dde4',
                'line-width': [
                    'interpolate',
                    ['linear'],
                    ['zoom'],
                    8,
                    0.2,
                    14,
                    1,
                ],
                'line-opacity': 0.45,
            },
        },
        {
            id: 'admin',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'admin',
            filter: ['==', ['get', 'maritime'], 0],
            paint: {
                'line-color': '#b4bccc',
                'line-width': 0.8,
                'line-opacity': 0.55,
                'line-dasharray': [3, 2],
            },
        },
        {
            id: 'place-label',
            type: 'symbol',
            source: 'mapbox-streets',
            'source-layer': 'place_label',
            filter: ['<=', ['get', 'symbolrank'], 14],
            layout: {
                'text-field': ['coalesce', ['get', 'name_en'], ['get', 'name']],
                'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
                'text-size': [
                    'interpolate',
                    ['linear'],
                    ['zoom'],
                    4,
                    9,
                    8,
                    11,
                    12,
                    12,
                ],
                'text-letter-spacing': 0.02,
            },
            paint: {
                'text-color': '#3d4d6a',
                'text-halo-color': '#eef0f2',
                'text-halo-width': 1.4,
                'text-opacity': 0.88,
            },
        },
    ],
};
