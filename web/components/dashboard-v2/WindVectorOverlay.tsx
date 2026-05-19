'use client';

import { useEffect, useRef } from 'react';
import type { Map as MapboxMap } from 'mapbox-gl';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField, WindVector } from '@/lib/wind/types';
import { buildWindLookup, interpolateWind, windSpeed } from '@/lib/wind/utils';

export type WindVizMode = 'vectors' | 'flow';

type WindVectorOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    mapReady?: boolean;
    active?: boolean;
};

/** Arrow color — bright enough for dark Mapbox basemap, still below track contrast. */
const ARROW_RGB = '186, 218, 236';

function arrowOpacity(speed: number): number {
    return Math.min(0.92, 0.62 + (speed / 40) * 0.3);
}

function arrowLength(speed: number): number {
    return Math.min(52, Math.max(16, speed * 1.45));
}

function drawArrow(ctx: CanvasRenderingContext2D, x: number, y: number, u: number, v: number, speed: number) {
    if (speed < 0.5) return;

    const len = arrowLength(speed);
    const dx = (u / speed) * len;
    const dy = (-v / speed) * len;
    const x2 = x + dx;
    const y2 = y + dy;
    const alpha = arrowOpacity(speed);
    const angle = Math.atan2(dy, dx);
    const head = 7;

    // Dark under-stroke for contrast on land/water
    ctx.strokeStyle = `rgba(8, 12, 18, ${alpha * 0.85})`;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    ctx.strokeStyle = `rgba(${ARROW_RGB}, ${alpha})`;
    ctx.fillStyle = `rgba(${ARROW_RGB}, ${alpha})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(angle - 0.42), y2 - head * Math.sin(angle - 0.42));
    ctx.lineTo(x2 - head * Math.cos(angle + 0.42), y2 - head * Math.sin(angle + 0.42));
    ctx.closePath();
    ctx.fill();
}

/** Screen-space fill between GFS grid points so vectors stay visible when zoomed out. */
function drawInterpolatedGrid(
    ctx: CanvasRenderingContext2D,
    map: MapboxMap,
    field: WindField,
    lookup: Map<string, WindVector>,
    cssW: number,
    cssH: number,
) {
    const zoom = map.getZoom();
    const spacing = zoom < 5 ? 72 : zoom < 6 ? 60 : zoom < 7 ? 48 : 40;
    const { bounds, gridResolution } = field;

    const pad = spacing / 2;
    for (let y = pad; y < cssH; y += spacing) {
        for (let x = pad; x < cssW; x += spacing) {
            const lngLat = map.unproject([x, y]);
            const wind = interpolateWind(lngLat.lat, lngLat.lng, lookup, bounds, gridResolution);
            drawArrow(ctx, x, y, wind.u, wind.v, windSpeed(wind));
        }
    }
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
    const rafMoveRef = useRef(0);

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
            const lookup = buildWindLookup(field);

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            const margin = 48;
            for (const pt of field.grid) {
                if (pt.lat < south || pt.lat > north) continue;
                if (west <= east) {
                    if (pt.lon < west || pt.lon > east) continue;
                } else if (pt.lon < west && pt.lon > east) continue;

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

            drawInterpolatedGrid(ctx, map, field, lookup, cssW, cssH);
        };

        drawRef.current = draw;

        const onMove = () => {
            cancelAnimationFrame(rafMoveRef.current);
            rafMoveRef.current = requestAnimationFrame(draw);
        };

        const onResize = () => {
            resize();
            draw();
        };

        const attach = () => {
            resize();
            draw();
            map.on('move', onMove);
            map.on('resize', onResize);
            window.addEventListener('resize', onResize);
        };

        if (map.isStyleLoaded()) attach();
        else map.once('load', attach);

        return () => {
            map.off('move', onMove);
            map.off('resize', onResize);
            window.removeEventListener('resize', onResize);
            cancelAnimationFrame(rafMoveRef.current);
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
