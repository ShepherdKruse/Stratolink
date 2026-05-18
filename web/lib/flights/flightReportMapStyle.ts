import type { FilterSpecification, StyleSpecification } from 'mapbox-gl';

/** Anchor cities only — coastal flight context, no interior clutter. */
export const FLIGHT_MAP_ANCHOR_CITIES = [
    'San Francisco',
    'Los Angeles',
    'San Diego',
    'Tijuana',
    'Ensenada',
] as const;

const anchorCityFilter = [
    'match',
    ['coalesce', ['get', 'name_en'], ['get', 'name']],
    ['literal', [...FLIGHT_MAP_ANCHOR_CITIES]],
    true,
    false,
] as const;

/** Duo-tone basemap: muted land/water, no roads, minimal labels. */
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
            id: 'water',
            type: 'fill',
            source: 'mapbox-streets',
            'source-layer': 'water',
            paint: { 'fill-color': '#dce4ec' },
        },
        {
            id: 'waterway',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'waterway',
            paint: {
                'line-color': '#d0dae6',
                'line-width': 0.6,
                'line-opacity': 0.7,
            },
        },
        {
            id: 'admin-country',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'admin',
            filter: ['all', ['==', ['get', 'maritime'], 0], ['==', ['get', 'admin_level'], 0]],
            paint: {
                'line-color': '#c5cad3',
                'line-width': 1.2,
                'line-opacity': 0.65,
            },
        },
        {
            id: 'admin-state',
            type: 'line',
            source: 'mapbox-streets',
            'source-layer': 'admin',
            filter: ['all', ['==', ['get', 'maritime'], 0], ['==', ['get', 'admin_level'], 1]],
            paint: {
                'line-color': '#d2d6de',
                'line-width': 0.7,
                'line-opacity': 0.5,
                'line-dasharray': [4, 3],
            },
        },
        {
            id: 'place-label',
            type: 'symbol',
            source: 'mapbox-streets',
            'source-layer': 'place_label',
            filter: anchorCityFilter as unknown as FilterSpecification,
            layout: {
                'text-field': ['coalesce', ['get', 'name_en'], ['get', 'name']],
                'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
                'text-size': 11,
                'text-letter-spacing': 0.04,
                'text-transform': 'uppercase',
            },
            paint: {
                'text-color': '#7a8599',
                'text-halo-color': '#eef0f2',
                'text-halo-width': 1.6,
                'text-opacity': 0.85,
            },
        },
    ],
};
