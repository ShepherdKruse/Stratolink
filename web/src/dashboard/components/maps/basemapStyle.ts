/**
 * The basemap shared by the homepage footer globe and the dashboard: the stock Mapbox light/dark styles reduced
 * to land, water, rivers, borders and place names (14 layers instead of 50). Generated from the stock styles by
 * `scripts/prepare-basemap-style.mjs` so colours and expressions match Mapbox's own; the code-added relief and
 * bathymetry (`baseStyle.ts`, `bathymetry.ts`) layer onto it exactly as they did onto the stock style.
 *
 * One style for both views means entering the dashboard from the footer never swaps styles, which used to
 * blank the globe mid-animation while Mapbox rebuilt it, and both views boot without parsing road, building and
 * land-use data they never showed.
 */
import type { StyleSpecification } from 'mapbox-gl';
import light from './basemap.light.json';
import dark from './basemap.dark.json';

export function basemapStyle(scheme: 'light' | 'dark'): StyleSpecification {
    return (scheme === 'dark' ? dark : light) as StyleSpecification;
}
