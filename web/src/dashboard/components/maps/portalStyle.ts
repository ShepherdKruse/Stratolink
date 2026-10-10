/**
 * Minimal basemap for the homepage footer globe.
 *
 * The stock light-v11 / dark-v11 styles carry 50 layers (roads, buildings, 14 label layers, …) that a
 * whole-globe preview never shows, yet every one of them costs style setup, tile parsing in the workers
 * and shader compilation on a phone before the first frame. This style keeps only what is visible at
 * globe zoom and uses the same composite tileset, so the code-added relief and bathymetry
 * (`applyBaseStyle`, `bathymetryAllZooms`) layer onto it exactly as they do onto the stock style.
 * Colours are copied from light-v11 / dark-v11. When the portal becomes the dashboard the stock style
 * replaces this one (see `mapStyle` in V2MissionMap).
 */
import type { StyleSpecification } from 'mapbox-gl';

const PALETTE = {
    light: { land: 'hsl(220, 3%, 99%)', water: 'hsl(220, 1%, 86%)', boundary: 'hsl(220, 0%, 70%)' },
    dark: { land: 'hsl(0, 0%, 16%)', water: 'hsl(0, 0%, 12%)', boundary: 'hsl(0, 0%, 41%)' },
} as const;

export function portalBasemapStyle(scheme: 'light' | 'dark'): StyleSpecification {
    const colors = PALETTE[scheme];
    return {
        version: 8,
        name: `stratolink-portal-${scheme}`,
        sources: {
            composite: { type: 'vector', url: 'mapbox://mapbox.mapbox-streets-v8,mapbox.mapbox-terrain-v2,mapbox.mapbox-bathymetry-v2' },
        },
        glyphs: 'mapbox://fonts/mapbox/{fontstack}/{range}.pbf', // balloon labels
        // Same sprite as the stock style: Mapbox cannot diff a sprite change, and without it the handoff to the
        // dashboard rebuilds the style from scratch (the globe blanks mid-animation). With it, the swap is incremental.
        sprite: `mapbox://sprites/mapbox/${scheme}-v11`,
        projection: { name: 'globe' },
        layers: [
            { id: 'land', type: 'background', paint: { 'background-color': colors.land } },
            { id: 'water', type: 'fill', source: 'composite', 'source-layer': 'water', paint: { 'fill-color': colors.water } },
            {
                id: 'admin-0-boundary', type: 'line', source: 'composite', 'source-layer': 'admin', minzoom: 1,
                filter: ['all', ['==', ['get', 'admin_level'], 0], ['==', ['get', 'disputed'], 'false'], ['==', ['get', 'maritime'], 'false'], ['match', ['get', 'worldview'], ['all', 'US'], true, false]],
                paint: { 'line-color': colors.boundary, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.65, 12, 2.6] },
            },
        ],
    };
}
