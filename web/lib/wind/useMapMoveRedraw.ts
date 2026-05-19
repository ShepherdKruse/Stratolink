import { useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';

/** Re-run draw on every map pan/zoom frame so canvas overlays stay georeferenced. */
export function useMapMoveRedraw(
    mapRef: React.RefObject<MapRef | null>,
    mapReady: boolean,
    draw: () => void,
    resize?: () => void,
) {
    const drawRef = useRef(draw);
    const resizeRef = useRef(resize);
    drawRef.current = draw;
    resizeRef.current = resize;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        if (!map || !mapReady) return;

        let raf = 0;
        const scheduleDraw = () => {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => drawRef.current());
        };

        const onResize = () => {
            resizeRef.current?.();
            scheduleDraw();
        };

        map.on('move', scheduleDraw);
        map.on('resize', onResize);
        window.addEventListener('resize', onResize);
        scheduleDraw();

        return () => {
            cancelAnimationFrame(raf);
            map.off('move', scheduleDraw);
            map.off('resize', onResize);
            window.removeEventListener('resize', onResize);
        };
    }, [mapRef, mapReady]);
}
