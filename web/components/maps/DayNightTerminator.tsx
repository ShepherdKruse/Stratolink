/**
 * Day/night terminator overlay.
 *
 * Adds a custom WebGL raster source (see `terminatorSource.ts`) that shades the
 * night hemisphere with a smooth, per-pixel twilight gradient computed from the
 * sun's current position, and refreshes it as the terminator drifts.
 *
 * Drop `<DayNightTerminator />` inside a react-map-gl `<Map>`. It manages its
 * own source/layer imperatively (custom sources aren't expressible as JSX), and
 * keeps the layer just beneath the data overlays so it dims only the basemap.
 */
'use client';

import { useEffect } from 'react';
import { useMap } from 'react-map-gl/mapbox';
import { TerminatorSource } from './terminatorSource';

const SRC_ID = 'sl-terminator';
const LAYER_ID = 'sl-terminator';
const NIGHT_OPACITY = 0.45;          /* overall darkness of full night */
const REFRESH_MS = 120_000;          /* terminator moves ~0.5°/2min */
const OVERLAY_RE = /^(tm-coverage|v2-)/;  /* data layers that must stay above */

export default function DayNightTerminator() {
    const { current: mapRef } = useMap();

    useEffect(() => {
        const map = mapRef?.getMap();
        if (!map) return;

        /* Keep the terminator just below the lowest data overlay so it dims the
         * basemap but never the flight path / gateways. */
        const position = () => {
            try {
                if (!map.getLayer(LAYER_ID)) return;
                const first = (map.getStyle()?.layers ?? []).find(l => OVERLAY_RE.test(l.id))?.id;
                if (first) map.moveLayer(LAYER_ID, first);
            } catch { /* ignore */ }
        };

        const ensure = () => {
            try {
                if (!map.getSource(SRC_ID)) {
                    map.addSource(SRC_ID, new TerminatorSource() as never);
                }
                if (!map.getLayer(LAYER_ID)) {
                    map.addLayer({
                        id: LAYER_ID,
                        type: 'raster',
                        source: SRC_ID,
                        paint: { 'raster-opacity': NIGHT_OPACITY, 'raster-fade-duration': 0 },
                    });
                }
                position();
            } catch { /* style mid-load; retry on next styledata */ }
        };

        ensure();
        map.on('styledata', ensure);

        const interval = setInterval(() => {
            const src = map.getSource(SRC_ID) as unknown as TerminatorSource | undefined;
            src?.setDate?.(new Date());
        }, REFRESH_MS);

        return () => {
            clearInterval(interval);
            map.off('styledata', ensure);
            try { if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID); } catch { /* ignore */ }
            try { if (map.getSource(SRC_ID)) map.removeSource(SRC_ID); } catch { /* ignore */ }
        };
    }, [mapRef]);

    return null;
}
