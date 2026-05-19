'use client';

import { useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField } from '@/lib/wind/types';
import { interpolateWind, windSpeed } from '@/lib/wind/utils';

type WindParticleOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    active?: boolean;
};

const PARTICLE_COUNT = 450;
const MAX_AGE = 60;

function speedColor(speed: number): string {
    const t = Math.min(1, speed / 35);
    const hue = 160 - t * 120;
    const sat = 55 + t * 25;
    const light = 48 + t * 12;
    return `hsla(${hue}, ${sat}%, ${light}%,`;
}

export default function WindParticleOverlay({ mapRef, windField, active = true }: WindParticleOverlayProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const particlesRef = useRef(
        Array.from({ length: PARTICLE_COUNT }, () => ({
            x: Math.random(),
            y: Math.random(),
            age: Math.floor(Math.random() * MAX_AGE),
            maxAge: MAX_AGE,
        })),
    );
    const rafRef = useRef(0);
    const windFieldRef = useRef(windField);
    const activeRef = useRef(active);
    const movingRef = useRef(false);

    windFieldRef.current = windField;
    activeRef.current = active;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let dpr = 1;
        let cssW = 0;
        let cssH = 0;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            cssW = rect.width;
            cssH = rect.height;
            canvas.width = Math.floor(cssW * dpr);
            canvas.height = Math.floor(cssH * dpr);
            canvas.style.width = `${cssW}px`;
            canvas.style.height = `${cssH}px`;
        };

        const clear = () => {
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };

        const drawParticles = () => {
            const field = windFieldRef.current;
            if (!field || !activeRef.current || movingRef.current || cssW === 0) {
                clear();
                return;
            }

            const { bounds, grid, gridResolution } = field;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, cssW, cssH);

            const sampleWind = (x: number, y: number) => {
                const lngLat = map.unproject([x, y]);
                return interpolateWind(lngLat.lat, lngLat.lng, grid, bounds, gridResolution);
            };

            particlesRef.current.forEach((p) => {
                const px = p.x * cssW;
                const py = p.y * cssH;
                const wind = sampleWind(px, py);
                const speed = windSpeed(wind);
                const scale = 0.35;
                const dx = wind.u * scale;
                const dy = -wind.v * scale;
                const nx = px + dx;
                const ny = py + dy;

                if (nx < 0 || nx > cssW || ny < 0 || ny > cssH || p.age > p.maxAge) {
                    p.x = Math.random();
                    p.y = Math.random();
                    p.age = 0;
                } else {
                    const alpha = Math.max(0, 1 - p.age / p.maxAge) * 0.5;
                    ctx.strokeStyle = `${speedColor(speed)}${alpha})`;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(px, py);
                    ctx.lineTo(nx, ny);
                    ctx.stroke();
                    p.x = nx / cssW;
                    p.y = ny / cssH;
                    p.age++;
                }
            });
        };

        const tick = () => {
            drawParticles();
            rafRef.current = requestAnimationFrame(tick);
        };

        const onMoveStart = () => {
            movingRef.current = true;
            clear();
        };

        const onMoveEnd = () => {
            movingRef.current = false;
            // Re-seed particles in view after pan/zoom
            particlesRef.current.forEach((p) => {
                p.x = Math.random();
                p.y = Math.random();
                p.age = 0;
            });
        };

        resize();
        map.on('movestart', onMoveStart);
        map.on('moveend', onMoveEnd);
        map.on('resize', resize);
        window.addEventListener('resize', resize);
        rafRef.current = requestAnimationFrame(tick);

        return () => {
            map.off('movestart', onMoveStart);
            map.off('moveend', onMoveEnd);
            map.off('resize', resize);
            window.removeEventListener('resize', resize);
            cancelAnimationFrame(rafRef.current);
        };
    }, [mapRef]);

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
