'use client';

import { useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField } from '@/lib/wind/types';
import { windSpeed } from '@/lib/wind/utils';

export type WindVizMode = 'vectors' | 'flow';

type WindVectorOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    mapReady?: boolean;
    active?: boolean;
};

function arrowOpacity(speed: number): number {
    return Math.min(0.55, 0.28 + (speed / 45) * 0.27);
}

function arrowLength(speed: number): number {
    return Math.min(42, Math.max(12, speed * 1.15));
}

function drawArrow(ctx: CanvasRenderingContext2D, x: number, y: number, u: number, v: number, speed: number) {
    if (speed < 0.8) return;

    const len = arrowLength(speed);
    const dx = (u / speed) * len;
    const dy = (-v / speed) * len;
    const x2 = x + dx;
    const y2 = y + dy;

    const alpha = arrowOpacity(speed);
    ctx.strokeStyle = `rgba(148, 188, 208, ${alpha})`;
    ctx.fillStyle = `rgba(148, 188, 208, ${alpha})`;
    ctx.lineWidth = 1.25;
    ctx.lineCap = 'round';

    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    const head = 5;
    const angle = Math.atan2(dy, dx);
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(angle - 0.45), y2 - head * Math.sin(angle - 0.45));
    ctx.lineTo(x2 - head * Math.cos(angle + 0.45), y2 - head * Math.sin(angle + 0.45));
    ctx.closePath();
    ctx.fill();
}

export default function WindVectorOverlay({
    mapRef,
    windField,
    mapReady = false,
    active = true,
}: WindVectorOverlayProps) {
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
        if (!map || !canvas || !mapReady) return;

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
            if (!field || !activeRef.current || cssW === 0 || field.grid.length === 0) return;

            const mapBounds = map.getBounds();
            if (!mapBounds) return;

            const west = mapBounds.getWest();
            const east = mapBounds.getEast();
            const south = mapBounds.getSouth();
            const north = mapBounds.getNorth();

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            const margin = 40;
            for (const pt of field.grid) {
                if (pt.lat < south || pt.lat > north) continue;
                if (west <= east) {
                    if (pt.lon < west || pt.lon > east) continue;
                } else {
                    // Antimeridian wrap
                    if (pt.lon < west && pt.lon > east) continue;
                }

                const screen = map.project([pt.lon, pt.lat]);
                if (
                    screen.x < -margin ||
                    screen.x > cssW + margin ||
                    screen.y < -margin ||
                    screen.y > cssH + margin
                ) {
                    continue;
                }

                drawArrow(ctx, screen.x, screen.y, pt.wind.u, pt.wind.v, windSpeed(pt.wind));
            }
        };

        drawRef.current = draw;

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

        const attach = () => {
            resize();
            draw();
            map.on('movestart', onMoveStart);
            map.on('moveend', onMoveEnd);
            map.on('resize', onResize);
            window.addEventListener('resize', onResize);
        };

        if (map.isStyleLoaded()) attach();
        else map.once('load', attach);

        return () => {
            map.off('movestart', onMoveStart);
            map.off('moveend', onMoveEnd);
            map.off('resize', onResize);
            window.removeEventListener('resize', onResize);
        };
    }, [mapRef, mapReady]);

    useEffect(() => {
        drawRef.current();
    }, [windField, active, mapReady]);

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
