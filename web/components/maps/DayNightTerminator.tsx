/**
 * Day/night terminator overlay.
 *
 * Adds custom WebGL raster sources (see `terminatorSource.ts`) that shade the
 * night hemisphere with a smooth, per-pixel twilight gradient computed from the
 * sun's current position, and refreshes them as the terminator drifts.
 *
 * Two separate layers so they can fade independently with zoom:
 *   - SHADE: a gentle dark tint on the night side — constant at all zooms, so
 *     the dark side stays dark however far you zoom in.
 *   - LIGHTS: NASA Black Marble city lights, composited lights-only (only the
 *     bright pixels paint, so the basemap shows through). These fade out by
 *     ~zoom 5.5 because the tileset is low-res and looks bad overzoomed.
 *
 * The fade lives on the LIGHTS layer's `raster-opacity` as a live map-zoom
 * expression — re-evaluated every frame across all tiles — so it applies
 * globally and reverses when you zoom back out (baking it into tile pixels did
 * neither). Drop `<DayNightTerminator />` inside a react-map-gl `<Map>`.
 */
'use client';

import { useEffect } from 'react';
import { useMap } from 'react-map-gl/mapbox';
import { TerminatorSource, type TerminatorBasemap } from './terminatorSource';

const SHADE_ID = 'sl-terminator-shade';
const LIGHTS_ID = 'sl-terminator-lights';

/* Night-shade strength (the layer scales the per-pixel tint). Dark mode dims a
 * touch more; both kept subtle so the basemap + UI read through. */
const SHADE_OPACITY_LIGHT = 0.3;
const SHADE_OPACITY_DARK = 0.42;
/* Peak city-light intensity (scaled by the zoom fade below). */
const LIGHTS_OPACITY = 0.9;

/* Live map-zoom fade for the lights: full strength while zoomed out, gone by
 * ~zoom 6.5 (the low-res lights look bad overzoomed). */
const lightsOpacityByZoom = [
    'interpolate', ['linear'], ['zoom'],
    5.5, LIGHTS_OPACITY,
    6.5, 0,
] as unknown;

const REFRESH_MS = 120_000;          /* terminator moves ~0.5°/2min */
const OVERLAY_RE = /^(tm-coverage|v2-)/;  /* data layers that must stay above */

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

type DayNightTerminatorProps = {
    /** Match map basemap — dark mode uses stronger day/night contrast. */
    colorScheme?: TerminatorBasemap;
};

export default function DayNightTerminator({ colorScheme = 'light' }: DayNightTerminatorProps) {
    const { current: mapRef } = useMap();
    /* Black-marble city lights need a token to fetch tiles. */
    const showLights = Boolean(MAPBOX_TOKEN);
    const shadeOpacity = colorScheme === 'dark' ? SHADE_OPACITY_DARK : SHADE_OPACITY_LIGHT;

    useEffect(() => {
        const map = mapRef?.getMap();
        if (!map) return;

        /* Keep the terminator layers below the basemap labels (symbol layers) and
         * data overlays, so they shade only the basemap fills/relief — country
         * labels, the flight path, and gateways all stay readable on top. Shade
         * first (lowest), then lights above it. */
        const position = () => {
            try {
                const layers = map.getStyle()?.layers ?? [];
                const anchor = layers.find(l => l.type === 'symbol' || OVERLAY_RE.test(l.id))?.id;
                if (!anchor) return;
                if (map.getLayer(SHADE_ID)) map.moveLayer(SHADE_ID, anchor);
                if (map.getLayer(LIGHTS_ID)) map.moveLayer(LIGHTS_ID, anchor);
            } catch { /* ignore */ }
        };

        const ensure = () => {
            try {
                /* SHADE — constant opacity at all zooms. */
                const shadeSrc = map.getSource(SHADE_ID) as unknown as TerminatorSource | undefined;
                if (!shadeSrc) {
                    map.addSource(SHADE_ID, new TerminatorSource({
                        id: SHADE_ID, kind: 'shade', basemap: colorScheme, maxzoom: 5,
                    }) as never);
                } else {
                    shadeSrc.setBasemap?.(colorScheme);
                }
                if (!map.getLayer(SHADE_ID)) {
                    map.addLayer({
                        id: SHADE_ID, type: 'raster', source: SHADE_ID,
                        paint: { 'raster-opacity': shadeOpacity, 'raster-fade-duration': 0 },
                    });
                } else {
                    map.setPaintProperty(SHADE_ID, 'raster-opacity', shadeOpacity);
                }

                /* LIGHTS — Black Marble, faded out by zoom. */
                if (showLights) {
                    const lightsSrc = map.getSource(LIGHTS_ID) as unknown as TerminatorSource | undefined;
                    if (!lightsSrc) {
                        map.addSource(LIGHTS_ID, new TerminatorSource({
                            id: LIGHTS_ID, kind: 'lights', basemap: colorScheme,
                            token: MAPBOX_TOKEN, blackMarble: true, maxzoom: 6,
                        }) as never);
                    } else {
                        lightsSrc.setBasemap?.(colorScheme);
                    }
                    if (!map.getLayer(LIGHTS_ID)) {
                        map.addLayer({
                            id: LIGHTS_ID, type: 'raster', source: LIGHTS_ID,
                            paint: { 'raster-opacity': lightsOpacityByZoom as never, 'raster-fade-duration': 0 },
                        });
                    }
                }

                position();
            } catch { /* style mid-load; retry on next styledata */ }
        };

        ensure();
        map.on('styledata', ensure);

        const interval = setInterval(() => {
            const now = new Date();
            (map.getSource(SHADE_ID) as unknown as TerminatorSource | undefined)?.setDate?.(now);
            (map.getSource(LIGHTS_ID) as unknown as TerminatorSource | undefined)?.setDate?.(now);
        }, REFRESH_MS);

        return () => {
            clearInterval(interval);
            map.off('styledata', ensure);
            for (const id of [LIGHTS_ID, SHADE_ID]) {
                try { if (map.getLayer(id)) map.removeLayer(id); } catch { /* ignore */ }
                try { if (map.getSource(id)) map.removeSource(id); } catch { /* ignore */ }
            }
        };
    }, [mapRef, colorScheme, shadeOpacity, showLights]);

    return null;
}
