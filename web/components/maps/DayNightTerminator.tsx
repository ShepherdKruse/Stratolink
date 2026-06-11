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

import { useEffect, useRef } from 'react';
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

const REFRESH_MS = 900_000;          /* re-render the terminator every 15 min */
const OVERLAY_RE = /^(tm-coverage|v2-)/;  /* data layers that must stay above */

/* Scrubbing the timeline would sweep the terminator across the map on every tick,
 * which reads as busy/distracting. Instead we HIDE it for the whole drag gesture
 * (driven by the `scrubbing` prop) and REVEAL it (fade-in) at the settled time on
 * release. */
const HIDE_MS = 80;             /* quick fade-out when a drag begins */
const TILE_REBUILD_MS = 80;     /* let tiles re-render at the new time before revealing */
const FADE_IN_MS = 140;         /* the reveal (after a scrub) */
/* The terminator is mounted only after the basemap has revealed, so its very
 * first appearance is a from-nothing fade. Make that one slower and gentler than
 * a scrub reveal, and give its tiles (the Black Marble night-lights especially) a
 * beat to arrive so they rise in with the shade rather than popping in after. */
const FIRST_REVEAL_DELAY_MS = 220;
const FIRST_REVEAL_FADE_MS = 650;       /* the city lights */
const FIRST_REVEAL_SHADE_FADE_MS = 1400; /* the night shadow — a long, gentle wash in */

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

type DayNightTerminatorProps = {
    /** Match map basemap — dark mode uses stronger day/night contrast. */
    colorScheme?: TerminatorBasemap;
    /** Instant (epoch ms or Date) the terminator should depict — e.g. the timeline
     *  scrub cursor, so day/night follows the time being viewed. Null/omitted =
     *  live: track the real current time and drift on a timer. */
    date?: number | Date | null;
    /** True while the user is actively dragging the scrubber. The terminator hides
     *  for the duration of the drag (so the shadow doesn't churn across the map)
     *  and fades back in at the settled `date` on release. */
    scrubbing?: boolean;
};

export default function DayNightTerminator({ colorScheme = 'light', date = null, scrubbing = false }: DayNightTerminatorProps) {
    const { current: mapRef } = useMap();
    /* Black-marble city lights need a token to fetch tiles. */
    const showLights = Boolean(MAPBOX_TOKEN);
    const shadeOpacity = colorScheme === 'dark' ? SHADE_OPACITY_DARK : SHADE_OPACITY_LIGHT;

    /* The setup effect (below) must not re-run on every scrub tick, but when it
     * (re)creates the sources it needs the *current* instant. Hold it in a ref the
     * setup reads, while a separate effect reacts to `date` changes. */
    const dateRef = useRef<number | Date | null>(date);
    dateRef.current = date;
    const resolveDate = () => {
        const d = dateRef.current;
        return d == null ? new Date() : new Date(d);
    };

    /* Direct handles to the source instances we create. `map.getSource(id)` for a
     * custom source returns Mapbox's wrapper, NOT our TerminatorSource — so
     * `getSource(id).setDate` is undefined and silently no-ops (which is why the
     * old timer never visibly moved the terminator). Call setDate on the real
     * instances instead. */
    const shadeSrcRef = useRef<TerminatorSource | null>(null);
    const lightsSrcRef = useRef<TerminatorSource | null>(null);

    /* Timer for the reveal-on-release fade-in. */
    const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    /* The first time we bring the layers up is a from-nothing fade (the layers
     * are created at opacity 0); later reveals are quicker scrub releases. */
    const firstRevealRef = useRef(true);

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
                /* Track whether we actually (re)created a layer this run. We must
                 * only reposition (moveLayer) when something changed — calling
                 * moveLayer unconditionally on every styledata is itself a style
                 * mutation that fires 'styledata', so it would loop forever and
                 * keep the map repainting every frame (the terminator's runaway
                 * CPU). Reposition only on first add / style reload. */
                let added = false;

                /* SHADE — constant opacity at all zooms. */
                const shadeSrc = map.getSource(SHADE_ID) as unknown as TerminatorSource | undefined;
                if (!shadeSrc) {
                    const src = new TerminatorSource({
                        id: SHADE_ID, kind: 'shade', basemap: colorScheme, maxzoom: 5, date: resolveDate(),
                    });
                    map.addSource(SHADE_ID, src as never);
                    shadeSrcRef.current = src;
                } else {
                    shadeSrcRef.current?.setBasemap?.(colorScheme);
                }
                if (!map.getLayer(SHADE_ID)) {
                    /* Created hidden; the date effect fades it up to target (a slow
                     * first-reveal fade on initial mount). */
                    map.addLayer({
                        id: SHADE_ID, type: 'raster', source: SHADE_ID,
                        paint: { 'raster-opacity': 0, 'raster-fade-duration': 0 },
                    });
                    added = true;
                }
                /* Do NOT re-apply raster-opacity on every styledata. The date effect
                 * owns shade opacity (it fades the shade out while scrubbing), and
                 * setPaintProperty itself fires 'styledata' → this handler — so a
                 * reset here would fight the fade and strobe. A colorScheme change
                 * re-runs the setup effect, which re-adds the layer at the right
                 * opacity, so the reset is redundant. */

                /* LIGHTS — Black Marble, faded out by zoom. */
                if (showLights) {
                    const lightsSrc = map.getSource(LIGHTS_ID) as unknown as TerminatorSource | undefined;
                    if (!lightsSrc) {
                        const src = new TerminatorSource({
                            id: LIGHTS_ID, kind: 'lights', basemap: colorScheme,
                            token: MAPBOX_TOKEN, blackMarble: true, maxzoom: 6, date: resolveDate(),
                        });
                        map.addSource(LIGHTS_ID, src as never);
                        lightsSrcRef.current = src;
                    } else {
                        lightsSrcRef.current?.setBasemap?.(colorScheme);
                    }
                    if (!map.getLayer(LIGHTS_ID)) {
                        /* Created hidden; faded up by the date effect. */
                        map.addLayer({
                            id: LIGHTS_ID, type: 'raster', source: LIGHTS_ID,
                            paint: { 'raster-opacity': 0, 'raster-fade-duration': 0 },
                        });
                        added = true;
                    }
                }

                if (added) position();
            } catch { /* style mid-load; retry on next styledata */ }
        };

        ensure();
        map.on('styledata', ensure);

        return () => {
            map.off('styledata', ensure);
            for (const id of [LIGHTS_ID, SHADE_ID]) {
                try { if (map.getLayer(id)) map.removeLayer(id); } catch { /* ignore */ }
                try { if (map.getSource(id)) map.removeSource(id); } catch { /* ignore */ }
            }
            shadeSrcRef.current = null;
            lightsSrcRef.current = null;
        };
    }, [mapRef, colorScheme, shadeOpacity, showLights]);

    /* Visibility + sun position. While `scrubbing` we hide the terminator and leave
     * its tiles frozen (no setDate ⇒ no churn ⇒ no flicker). On release we rebuild
     * at the settled `date` while still hidden, then fade in. Live (date null) shows
     * "now" and drifts on a slow timer. Kept out of the setup effect so this never
     * tears down/rebuilds the layers. */
    useEffect(() => {
        const map = mapRef?.getMap();
        if (!map) return;

        const setDate = (d: Date) => {
            shadeSrcRef.current?.setDate(d);
            lightsSrcRef.current?.setDate(d);
        };
        const setOpacity = (id: string, value: unknown, durationMs: number) => {
            if (!map.getLayer(id)) return;
            try {
                map.setPaintProperty(id, 'raster-opacity-transition', { duration: durationMs, delay: 0 });
                map.setPaintProperty(id, 'raster-opacity', value as never);
            } catch { /* layer mid-(re)build */ }
        };
        const clearReveal = () => {
            if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
            revealTimerRef.current = null;
        };

        clearReveal();

        if (scrubbing) {
            /* Hide for the whole drag — frozen tiles, no rebuilds. */
            setOpacity(SHADE_ID, 0, HIDE_MS);
            setOpacity(LIGHTS_ID, 0, HIDE_MS);
            return;
        }

        /* Not scrubbing: rebuild at the target instant while (possibly) hidden, then
         * fade in once the tiles have re-rendered. Covers release, map-click jumps,
         * and release-back-to-live (date null ⇒ now). The very first reveal (after
         * the deferred mount) is slower and waits a touch longer for tiles. */
        setDate(date != null ? new Date(date) : new Date());
        const first = firstRevealRef.current;
        firstRevealRef.current = false;
        const delayMs = first ? FIRST_REVEAL_DELAY_MS : TILE_REBUILD_MS;
        const shadeFadeMs = first ? FIRST_REVEAL_SHADE_FADE_MS : FADE_IN_MS;
        const lightsFadeMs = first ? FIRST_REVEAL_FADE_MS : FADE_IN_MS;
        revealTimerRef.current = setTimeout(() => {
            setOpacity(SHADE_ID, shadeOpacity, shadeFadeMs);
            setOpacity(LIGHTS_ID, lightsOpacityByZoom, lightsFadeMs);
        }, delayMs);

        if (date != null) return clearReveal;
        const interval = setInterval(() => setDate(new Date()), REFRESH_MS);
        return () => { clearReveal(); clearInterval(interval); };
    }, [mapRef, date, scrubbing, shadeOpacity]);

    return null;
}
