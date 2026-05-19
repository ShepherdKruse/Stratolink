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
    const lookupRef = useRef<Map<string, import('@/lib/wind/types').WindVector> | null>(null);
    const activeRef = useRef(active);
    const particlesRef = useRef<Particle[]>([]);
    const rafRef = useRef(0);
    const movingRef = useRef(false);

    windFieldRef.current = windField;
    activeRef.current = active;
    if (windField) lookupRef.current = buildWindLookup(windField);

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas || !mapReady) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const N = 650;
        const MAX = 55;
        const DT = 1.4e-4;
        let frameSkip = 0;

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
                max: 35 + Math.floor(Math.random() * 25),
                px: null,
                py: null,
            };
        };

        const seed = (m: MapboxMap) => {
            particlesRef.current = Array.from({ length: N }, () => spawnOne(m));
        };

        let running = false;

        const frame = () => {
            if (!running) return;
            rafRef.current = requestAnimationFrame(frame);

            if (movingRef.current) return;

            frameSkip++;
            if (frameSkip % 2 !== 0) return;

            const field = windFieldRef.current;
            const lookup = lookupRef.current;
            const m = mapRef.current?.getMap();
            if (!m || !field || !lookup || !activeRef.current) return;

            const { bounds, gridResolution } = field;
            const W = canvas.width;
            const H = canvas.height;

            ctx.fillStyle = 'rgba(8,13,23,0.14)';
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
                    const alpha = Math.min(0.22, life * (0.06 + sn * 0.16));
                    const r = Math.round(120 + sn * 90);
                    const g = Math.round(170 + sn * 50);

                    ctx.beginPath();
                    ctx.moveTo(p.px, p.py);
                    ctx.lineTo(x, y);
                    ctx.strokeStyle = `rgba(${r},${g},248,${alpha.toFixed(2)})`;
                    ctx.lineWidth = 0.4 + sn * 0.7;
                    ctx.stroke();
                }

                p.px = x;
                p.py = y;

                if (p.age >= p.max || x < -8 || x > W + 8 || y < -8 || y > H + 8) {
                    Object.assign(p, spawnOne(m));
                }
            }
        };

        const clear = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };

        const start = () => {
            if (running) return;
            running = true;
            rafRef.current = requestAnimationFrame(frame);
        };

        const stop = () => {
            running = false;
            cancelAnimationFrame(rafRef.current);
            clear();
        };

        const onMoveStart = () => {
            movingRef.current = true;
            clear();
        };

        const onMoveEnd = () => {
            movingRef.current = false;
            particlesRef.current.forEach((p) => {
                p.px = null;
                p.py = null;
            });
        };

        const attach = () => {
            resize();
            seed(map);
            if (activeRef.current && windFieldRef.current) start();
            map.on('movestart', onMoveStart);
            map.on('moveend', onMoveEnd);
            window.addEventListener('resize', resize);
        };

        if (map.isStyleLoaded()) attach();
        else map.once('load', attach);

        return () => {
            stop();
            map.off('movestart', onMoveStart);
            map.off('moveend', onMoveEnd);
            window.removeEventListener('resize', resize);
        };
    }, [mapRef, mapReady, windField, active]);

    return (
        <canvas
            ref={canvasRef}
            className="wind-synthesis-wind-canvas"
            style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 2,
                opacity: 0.85,
            }}
        />
    );
}
