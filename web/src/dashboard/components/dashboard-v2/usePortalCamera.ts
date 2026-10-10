import { useEffect, useRef, type RefObject } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';
import type { ExpressionSpecification, Map as MapboxMap } from 'mapbox-gl';
import { notifyGlobeParent, type GlobeStage } from './globe-portal';

const portalLabelVisibility = new WeakMap<MapboxMap, Map<string, 'visible' | 'none' | ExpressionSpecification>>();

/** A theme style load must keep the footer's basemap labels hidden too. */
export function applyPortalLabelVisibility(map: MapboxMap, stage: GlobeStage) {
    if (stage === 'standalone') return;
    /* The portal swaps its lean basemap for the stock style as it becomes the dashboard; reading layers mid-load throws. */
    if (!map.isStyleLoaded()) { map.once('style.load', () => applyPortalLabelVisibility(map, stage)); return; }
    let visibility = portalLabelVisibility.get(map);
    if (!visibility) {
        visibility = new Map();
        portalLabelVisibility.set(map, visibility);
    }
    for (const layer of map.getStyle()?.layers ?? []) {
        if (layer.type !== 'symbol' || layer.id.startsWith('v2-')) continue;
        const current = layer.layout?.visibility ?? 'visible';
        if (!visibility.has(layer.id) || current !== 'none') visibility.set(layer.id, current);
        map.setLayoutProperty(layer.id, 'visibility', stage === 'dashboard' ? visibility.get(layer.id) : 'none');
    }
}

/** The footer and dashboard share this Mapbox instance throughout navigation. */
export function usePortalCamera(mapRef: RefObject<MapRef | null>, stage: GlobeStage, ready: boolean, balloons: Array<{lat: number; lon: number}>) {
    const center = useRef<[number, number]>([-55, 25]);
    const configured = useRef(false);
    const lastStage = useRef(stage);
    const points = useRef(balloons);
    points.current = balloons;
    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || !ready || stage === 'standalone') return;
        let frame = 0;
        let observer: ResizeObserver | undefined;
        let onPreviewReady: (() => void) | undefined;
        let previewVisible = false;
        let updateRotation = () => {};
        function receive(event: MessageEvent) {
            if (event.origin === location.origin && event.source === window.parent && event.data?.channel === 'stratolink-globe' && typeof event.data.previewVisible === 'boolean') {
                previewVisible = event.data.previewVisible;
                updateRotation();
            }
        }
        window.addEventListener('message', receive);
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        // Keep only balloon labels on the footer globe. Basemap labels can
        // otherwise project outside the sphere's edge during the rotation.
        applyPortalLabelVisibility(map, stage);
        const globeZoom = () => Math.log2(Math.min(innerWidth, innerHeight) * .82 * Math.PI / 512);
        if (stage === 'footer') {
            map.stop();
            if (!configured.current || lastStage.current !== 'footer') {
                const fleet = points.current;
                if (fleet.length) {
                    const x = fleet.reduce((sum, p) => sum + Math.cos(p.lon * Math.PI / 180), 0);
                    const y = fleet.reduce((sum, p) => sum + Math.sin(p.lon * Math.PI / 180), 0);
                    center.current = [Math.atan2(y, x) * 180 / Math.PI, Math.min(45, Math.max(-45, fleet.reduce((sum, p) => sum + p.lat, 0) / fleet.length))];
                }
                configured.current = true;
            }
            const layout = () => { map.resize(); map.jumpTo({ center: center.current, zoom: globeZoom(), bearing: 0, pitch: 0, padding: {top:0,bottom:0,left:0,right:0} }); };
            layout();
            observer = new ResizeObserver(layout);
            observer.observe(document.documentElement);
            if (!reduced) {
                let previous = performance.now();
                const drift = (now: number) => {
                    frame = 0;
                    const elapsed = Math.min(now - previous, 64);
                    previous = now;
                    if (previewVisible && !document.hidden) {
                        center.current = [(center.current[0] + elapsed * .002) % 360, center.current[1]];
                        map.jumpTo({ center: center.current });
                    }
                    if (previewVisible && !document.hidden) frame = requestAnimationFrame(drift);
                };
                updateRotation = () => {
                    if (previewVisible && !document.hidden && !frame) {
                        previous = performance.now();
                        frame = requestAnimationFrame(drift);
                    } else if (!previewVisible || document.hidden) {
                        cancelAnimationFrame(frame);
                        frame = 0;
                    }
                };
            }
            // A return from a dark dashboard first restores the light style.
            // Show the footer globe only after that style has finished drawing.
            const timing = ((window as unknown as { __mapTiming?: Record<string, number> }).__mapTiming ??= {});
            timing.fleetReady ??= Math.round(performance.now());
            onPreviewReady = () => { timing.readySent ??= Math.round(performance.now()); notifyGlobeParent('ready'); };
            map.once('idle', onPreviewReady);
            map.triggerRepaint();
        } else if (stage === 'entering') {
            const start = performance.now();
            const duration = reduced ? 180 : 1600;
            const spin = (now: number) => {
                const t = Math.min(1, (now - start) / duration);
                const ease = t * t * (3 - 2 * t);
                map.jumpTo({ center: [center.current[0] + (reduced ? 0 : 360 * ease), center.current[1]], zoom: globeZoom(), bearing:0, pitch:0, padding:{top:0,bottom:0,left:0,right:0} });
                if (t < 1) frame = requestAnimationFrame(spin);
                else { map.jumpTo({ center: center.current }); notifyGlobeParent('arrived'); }
            };
            frame = requestAnimationFrame(spin);
        } else {
            const panel = document.querySelector('.fleet-panel');
            const position = () => {
                const mobile = innerWidth < 768;
                const bounds = panel?.getBoundingClientRect();
                const left = mobile ? 0 : (bounds?.width ?? 420);
                const top = mobile ? Math.min(bounds?.height ?? 350, innerHeight * .55) : 0;
                document.documentElement.style.setProperty('--portal-panel-height', `${top}px`);
                map.easeTo({ padding:{left, top, right:0, bottom:mobile ? 40 : 0}, duration:reduced ? 0 : 700 });
            };
            position();
            if (panel) { observer = new ResizeObserver(position); observer.observe(panel); }
        }
        document.addEventListener('visibilitychange', updateRotation);
        lastStage.current = stage;
        return () => { cancelAnimationFrame(frame); observer?.disconnect(); if (onPreviewReady) map.off('idle', onPreviewReady); window.removeEventListener('message', receive); document.removeEventListener('visibilitychange', updateRotation); map.stop(); };
    }, [mapRef, stage, ready]);
}
