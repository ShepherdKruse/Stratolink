'use client';

import { useCallback, useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField } from '@/lib/wind/types';
import { interpolateWind, windSpeed } from '@/lib/wind/utils';

type TrackLine = {
    coords: Array<{ lat: number; lon: number }>;
    color: string;
    dashed?: boolean;
    width?: number;
};

type WindParticleOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    tracks: TrackLine[];
    active?: boolean;
};

const PARTICLE_COUNT = 1200;
const MAX_AGE = 70;

function speedColor(speed: number): string {
    const t = Math.min(1, speed / 35);
    const hue = 160 - t * 120;
    const sat = 55 + t * 25;
    const light = 48 + t * 12;
    return `hsla(${hue}, ${sat}%, ${light}%,`;
}

export default function WindParticleOverlay({
    mapRef,
    windField,
    tracks,
    active = true,
}: WindParticleOverlayProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const particlesRef = useRef(
        Array.from({ length: PARTICLE_COUNT }, () => ({
            x: Math.random(),
            y: Math.random(),
            age: Math.floor(Math.random() * MAX_AGE),
            maxAge: MAX_AGE,
        })),
    );
    const rafRef = useRef<number>(0);

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        const map = mapRef.current?.getMap();
        if (!canvas || !map || !active) return;

        const w = canvas.width;
        const h = canvas.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, w, h);

        if (windField) {
            const { bounds, grid, gridResolution } = windField;

            const sampleWind = (x: number, y: number) => {
                const lngLat = map.unproject([x, y]);
                return interpolateWind(lngLat.lat, lngLat.lng, grid, bounds, gridResolution);
            };

            // Wind particles (nullschool-style streamlines)
            particlesRef.current.forEach((p) => {
            const px = p.x * w;
            const py = p.y * h;
            const wind = sampleWind(px, py);
            const speed = windSpeed(wind);
            const scale = 0.35;
            const dx = wind.u * scale;
            const dy = -wind.v * scale;

            const nx = px + dx;
            const ny = py + dy;

            if (nx < 0 || nx > w || ny < 0 || ny > h || p.age > p.maxAge) {
                p.x = Math.random();
                p.y = Math.random();
                p.age = 0;
            } else {
                const alpha = Math.max(0, 1 - p.age / p.maxAge) * 0.55;
                ctx.strokeStyle = `${speedColor(speed)}${alpha})`;
                ctx.lineWidth = 1.1;
                ctx.beginPath();
                ctx.moveTo(px, py);
                ctx.lineTo(nx, ny);
                ctx.stroke();
                p.x = nx / w;
                p.y = ny / h;
                p.age++;
            }
            });
        }

        // Tracks on top of wind (projected to screen)
        for (const track of tracks) {
            if (track.coords.length < 2) continue;
            const projected = track.coords
                .map((c) => map.project([c.lon, c.lat]))
                .filter((p) => Number.isFinite(p.x));

            ctx.save();
            if (track.dashed) ctx.setLineDash([6, 4]);
            ctx.strokeStyle = track.color;
            ctx.lineWidth = track.width ?? 2.5;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.shadowColor = track.color;
            ctx.shadowBlur = 6;
            ctx.beginPath();
            projected.forEach((pt, i) => {
                if (i === 0) ctx.moveTo(pt.x, pt.y);
                else ctx.lineTo(pt.x, pt.y);
            });
            ctx.stroke();
            ctx.restore();
        }

        rafRef.current = requestAnimationFrame(draw);
    }, [mapRef, windField, tracks, active]);

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas) return;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            canvas.width = rect.width * devicePixelRatio;
            canvas.height = rect.height * devicePixelRatio;
            canvas.style.width = `${rect.width}px`;
            canvas.style.height = `${rect.height}px`;
        };

        resize();
        const onMove = () => draw();
        map.on('move', onMove);
        map.on('resize', resize);
        window.addEventListener('resize', resize);
        rafRef.current = requestAnimationFrame(draw);

        return () => {
            map.off('move', onMove);
            map.off('resize', resize);
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(rafRef.current);
        };
    }, [mapRef, draw]);

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
