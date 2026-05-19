'use client';

import { useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField } from '@/lib/wind/types';
import { interpolateWind, windSpeed } from '@/lib/wind/utils';

export type WindVizMode = 'vectors' | 'flow';

type WindVectorOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    active?: boolean;
};

function gridSpacing(zoom: number): number {
    if (zoom < 4) return 0;
    if (zoom < 5) return 140;
    if (zoom < 6) return 110;
    if (zoom < 7) return 90;
    return 72;
}

function arrowOpacity(speed: number): number {
    return Math.min(0.48, 0.2 + (speed / 45) * 0.28);
}

function arrowLength(speed: number): number {
    return Math.min(38, Math.max(10, speed * 1.1));
}

function drawArrow(ctx: CanvasRenderingContext2D, x: number, y: number, u: number, v: number, speed: number) {
    if (speed < 1.5) return;

    const len = arrowLength(speed);
    const dx = (u / speed) * len;
    const dy = (-v / speed) * len;
    const x2 = x + dx;
    const y2 = y + dy;

    const alpha = arrowOpacity(speed);
    ctx.strokeStyle = `rgba(130, 168, 186, ${alpha})`;
    ctx.fillStyle = `rgba(130, 168, 186, ${alpha})`;
    ctx.lineWidth = 1.15;
    ctx.lineCap = 'round';

    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    const head = 4;
    const angle = Math.atan2(dy, dx);
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(angle - 0.45), y2 - head * Math.sin(angle - 0.45));
    ctx.lineTo(x2 - head * Math.cos(angle + 0.45), y2 - head * Math.sin(angle + 0.45));
    ctx.closePath();
    ctx.fill();
}

export default function WindVectorOverlay({ mapRef, windField, active = true }: WindVectorOverlayProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const windFieldRef = useRef(windField);
    const activeRef = useRef(active);
    const layoutRef = useRef({ dpr: 1, cssW: 0, cssH: 0 });
    const drawRef = useRef<() => void>(() => {});

    windFieldRef.current = windField;
    activeRef.current = active;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            layoutRef.current = { dpr, cssW: rect.width, cssH: rect.height };
            canvas.width = Math.floor(rect.width * dpr);
            canvas.height = Math.floor(rect.height * dpr);
            canvas.style.width = `${rect.width}px`;
            canvas.style.height = `${rect.height}px`;
        };

        const draw = () => {
            const { dpr, cssW, cssH } = layoutRef.current;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const field = windFieldRef.current;
            if (!field || !activeRef.current || cssW === 0) return;

            const spacing = gridSpacing(map.getZoom());
            if (spacing === 0) return;

            const { bounds, grid, gridResolution } = field;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            const pad = spacing / 2;
            for (let y = pad; y < cssH; y += spacing) {
                for (let x = pad; x < cssW; x += spacing) {
                    const lngLat = map.unproject([x, y]);
                    const wind = interpolateWind(lngLat.lat, lngLat.lng, grid, bounds, gridResolution);
                    drawArrow(ctx, x, y, wind.u, wind.v, windSpeed(wind));
                }
            }
        };

        drawRef.current = draw;
        resize();
        draw();

        const clear = () => {
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };

        const onMoveStart = () => clear();
        const onMoveEnd = () => draw();
        const onResize = () => {
            resize();
            draw();
        };

        map.on('movestart', onMoveStart);
        map.on('moveend', onMoveEnd);
        map.on('resize', onResize);
        window.addEventListener('resize', onResize);

        return () => {
            map.off('movestart', onMoveStart);
            map.off('moveend', onMoveEnd);
            map.off('resize', onResize);
            window.removeEventListener('resize', onResize);
        };
    }, [mapRef]);

    useEffect(() => {
        drawRef.current();
    }, [windField, active]);

    return (
        <canvas
            ref={canvasRef}
            style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 2,
            }}
        />
    );
}
