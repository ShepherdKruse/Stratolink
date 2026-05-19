'use client';

import { useCallback, useEffect, useRef } from 'react';
import type { Map as MapboxMap } from 'mapbox-gl';
import type { MapRef } from 'react-map-gl/mapbox';
import { useMapMoveRedraw } from '@/lib/wind/useMapMoveRedraw';

export type TrackStroke = {
    coords: Array<[number, number]>;
    color: string;
    width: number;
    dashed?: boolean;
    halo?: boolean;
    haloColor?: string;
    haloWidth?: number;
};

type FlightTrackOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    mapReady?: boolean;
    tracks: TrackStroke[];
};

function drawLine(
    ctx: CanvasRenderingContext2D,
    map: MapboxMap,
    coords: Array<[number, number]>,
    color: string,
    width: number,
    dashed?: boolean,
    halo?: boolean,
    haloColor = '#000',
    haloWidth = 10,
) {
    if (coords.length < 2) return;
    const pts = coords.map(([lon, lat]) => map.project([lon, lat])).filter((p) => Number.isFinite(p.x));
    if (pts.length < 2) return;

    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    if (dashed) ctx.setLineDash([6, 5]);

    if (halo) {
        ctx.strokeStyle = haloColor;
        ctx.lineWidth = haloWidth;
        ctx.globalAlpha = 0.45;
        ctx.beginPath();
        pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.stroke();
    ctx.restore();
}

export default function FlightTrackOverlay({ mapRef, mapReady = false, tracks }: FlightTrackOverlayProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const tracksRef = useRef(tracks);
    tracksRef.current = tracks;

    const layoutRef = useRef({ dpr: 1, cssW: 0, cssH: 0 });

    const resize = useCallback(() => {
        const canvas = canvasRef.current;
        const parent = canvas?.parentElement;
        if (!canvas || !parent) return;
        const rect = parent.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        layoutRef.current = { dpr, cssW: rect.width, cssH: rect.height };
        canvas.width = Math.floor(rect.width * dpr);
        canvas.height = Math.floor(rect.height * dpr);
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
    }, []);

    const draw = useCallback(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const { dpr, cssW, cssH } = layoutRef.current;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (cssW === 0) return;

        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        for (const t of tracksRef.current) {
            drawLine(ctx, map, t.coords, t.color, t.width, t.dashed, t.halo, t.haloColor, t.haloWidth);
        }
    }, [mapRef]);

    useMapMoveRedraw(mapRef, mapReady, draw, resize);

    useEffect(() => {
        draw();
    }, [tracks, draw]);

    return (
        <canvas
            ref={canvasRef}
            className="wind-synthesis-track-canvas"
            style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 6,
            }}
        />
    );
}
