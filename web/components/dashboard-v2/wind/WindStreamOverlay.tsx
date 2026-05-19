'use client';

import { useEffect, useRef } from 'react';
import type { Map as MapboxMap } from 'mapbox-gl';
import type { MapRef } from 'react-map-gl/mapbox';
import type { WindField } from '@/lib/wind/types';
import { buildWindLookup, interpolateWind, windSpeed } from '@/lib/wind/utils';

type WindStreamOverlayProps = {
    mapRef: React.RefObject<MapRef | null>;
    windField: WindField | null;
    mapReady?: boolean;
    active?: boolean;
};

type Particle = {
    lat: number;
    lon: number;
    age: number;
    max: number;
    px: number | null;
    py: number | null;
};

export default function WindStreamOverlay({
    mapRef,
    windField,
    mapReady = false,
    active = true,
}: WindStreamOverlayProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const windFieldRef = useRef(windField);
    const activeRef = useRef(active);
    const particlesRef = useRef<Particle[]>([]);
    const rafRef = useRef(0);

    windFieldRef.current = windField;
    activeRef.current = active;

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas || !mapReady) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const N = 2000;
        const MAX = 65;
        const DT = 1.4e-4;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
            particlesRef.current.forEach((p) => {
                p.px = null;
                p.py = null;
            });
        };

        const spawnOne = (m: MapboxMap): Particle => {
            const b = m.getBounds();
            if (!b) return { lat: 35, lon: -100, age: 0, max: 50, px: null, py: null };
            return {
                lat: b.getSouth() + Math.random() * (b.getNorth() - b.getSouth()),
                lon: b.getWest() + Math.random() * (b.getEast() - b.getWest()),
                age: Math.floor(Math.random() * MAX),
                max: 40 + Math.floor(Math.random() * 38),
                px: null,
                py: null,
            };
        };

        const seed = (m: MapboxMap) => {
            particlesRef.current = Array.from({ length: N }, () => spawnOne(m));
        };

        const resetPositions = () => {
            particlesRef.current.forEach((p) => {
                p.px = null;
                p.py = null;
            });
        };

        let running = false;

        const frame = () => {
            if (!running) return;

            const field = windFieldRef.current;
            const m = mapRef.current?.getMap();
            if (!m || !field || !activeRef.current) {
                rafRef.current = requestAnimationFrame(frame);
                return;
            }

            const lookup = buildWindLookup(field);
            const { bounds, gridResolution } = field;
            const W = canvas.width;
            const H = canvas.height;

            ctx.fillStyle = 'rgba(8,13,23,0.068)';
            ctx.fillRect(0, 0, W, H);

            for (const p of particlesRef.current) {
                const wind = interpolateWind(p.lat, p.lon, lookup, bounds, gridResolution);
                const spd = windSpeed(wind);
                if (spd < 0.8) {
                    p.age++;
                    continue;
                }

                const cl = Math.cos((p.lat * Math.PI) / 180);
                p.lat += wind.v * DT;
                p.lon += (wind.u * DT) / Math.max(cl, 0.08);
                p.age++;

                const sc = m.project([p.lon, p.lat]);
                const x = sc.x;
                const y = sc.y;

                if (p.px !== null && p.py !== null) {
                    const life = Math.sin((p.age / p.max) * Math.PI);
                    const sn = Math.min(spd / 42, 1);
                    const alpha = life * (0.12 + sn * 0.38);
                    const r = Math.round(120 + sn * 110);
                    const g = Math.round(170 + sn * 70);

                    ctx.beginPath();
                    ctx.moveTo(p.px, p.py);
                    ctx.lineTo(x, y);
                    ctx.strokeStyle = `rgba(${r},${g},248,${alpha.toFixed(2)})`;
                    ctx.lineWidth = 0.5 + sn * 1.1;
                    ctx.stroke();
                }

                p.px = x;
                p.py = y;

                if (p.age >= p.max || x < -8 || x > W + 8 || y < -8 || y > H + 8) {
                    Object.assign(p, spawnOne(m));
                }
            }

            rafRef.current = requestAnimationFrame(frame);
        };

        const start = () => {
            if (running) return;
            running = true;
            rafRef.current = requestAnimationFrame(frame);
        };

        const stop = () => {
            running = false;
            cancelAnimationFrame(rafRef.current);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };

        const onMove = () => resetPositions();

        const attach = () => {
            resize();
            seed(map);
            if (activeRef.current && windFieldRef.current) start();
            map.on('move', onMove);
            window.addEventListener('resize', resize);
        };

        if (map.isStyleLoaded()) attach();
        else map.once('load', attach);

        return () => {
            stop();
            map.off('move', onMove);
            window.removeEventListener('resize', resize);
        };
    }, [mapRef, mapReady, windField, active]);

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
