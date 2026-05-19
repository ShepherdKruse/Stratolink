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

/** Tune stream visibility: continent view needs thicker, slower-fading, faster-advecting strokes. */
function streamProfile(zoom: number) {
    const z = Math.max(2, Math.min(12, zoom));
    const wide = Math.max(0, Math.min(1, (7.5 - z) / 4.5));

    return {
        particleCount: Math.round(750 + wide * 550),
        dt: 1.4e-4 * Math.pow(2, (7.5 - z) * 0.58),
        fade: Math.max(0.035, 0.11 - wide * 0.065),
        lineWidthBase: 0.55 + wide * 3.2,
        lineWidthSpeed: 0.75 + wide * 2.0,
        alphaMax: 0.4 + wide * 0.42,
        alphaSpeedScale: 0.1 + wide * 0.3,
        maxAge: Math.round(48 + wide * 42),
    };
}

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
    const lastZoomRef = useRef(0);

    windFieldRef.current = windField;
    activeRef.current = active;
    if (windField) lookupRef.current = buildWindLookup(windField);

    useEffect(() => {
        const map = mapRef.current?.getMap();
        const canvas = canvasRef.current;
        if (!map || !canvas || !mapReady || !active) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const resize = () => {
            const parent = canvas.parentElement;
            if (!parent) return;
            const rect = parent.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.floor(rect.width * dpr);
            canvas.height = Math.floor(rect.height * dpr);
            canvas.style.width = `${rect.width}px`;
            canvas.style.height = `${rect.height}px`;
            particlesRef.current.forEach((p) => {
                p.px = null;
                p.py = null;
            });
        };

        const spawnOne = (m: MapboxMap, maxAge: number): Particle => {
            const b = m.getBounds();
            if (!b) return { lat: 35, lon: -100, age: 0, max: maxAge, px: null, py: null };
            return {
                lat: b.getSouth() + Math.random() * (b.getNorth() - b.getSouth()),
                lon: b.getWest() + Math.random() * (b.getEast() - b.getWest()),
                age: Math.floor(Math.random() * maxAge),
                max: Math.round(maxAge * 0.65 + Math.random() * maxAge * 0.35),
                px: null,
                py: null,
            };
        };

        const syncParticleCount = (m: MapboxMap, target: number, maxAge: number) => {
            const list = particlesRef.current;
            while (list.length < target) list.push(spawnOne(m, maxAge));
            while (list.length > target) list.pop();
        };

        const resetTrails = () => {
            particlesRef.current.forEach((p) => {
                p.px = null;
                p.py = null;
            });
        };

        let running = true;

        const frame = () => {
            if (!running) return;
            rafRef.current = requestAnimationFrame(frame);

            const field = windFieldRef.current;
            const lookup = lookupRef.current;
            const m = mapRef.current?.getMap();
            if (!m || !field || !lookup || !activeRef.current) return;

            const zoom = m.getZoom();
            if (Math.abs(zoom - lastZoomRef.current) > 0.35) {
                resetTrails();
                lastZoomRef.current = zoom;
            }

            const profile = streamProfile(zoom);
            syncParticleCount(m, profile.particleCount, profile.maxAge);

            const { bounds, gridResolution } = field;
            const W = canvas.width;
            const H = canvas.height;
            const dpr = W / (canvas.clientWidth || W);

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            const cssW = canvas.clientWidth || W / dpr;
            const cssH = canvas.clientHeight || H / dpr;

            ctx.globalCompositeOperation = 'destination-out';
            ctx.fillStyle = `rgba(0,0,0,${profile.fade})`;
            ctx.fillRect(0, 0, cssW, cssH);
            ctx.globalCompositeOperation = 'source-over';

            for (const p of particlesRef.current) {
                const wind = interpolateWind(p.lat, p.lon, lookup, bounds, gridResolution);
                const spd = windSpeed(wind);
                if (spd < 0.8) {
                    p.age++;
                    continue;
                }

                const cl = Math.cos((p.lat * Math.PI) / 180);
                p.lat += wind.v * profile.dt;
                p.lon += (wind.u * profile.dt) / Math.max(cl, 0.08);
                p.age++;

                const sc = m.project([p.lon, p.lat]);
                const x = sc.x;
                const y = sc.y;

                if (p.px !== null && p.py !== null) {
                    const life = Math.sin((p.age / p.max) * Math.PI);
                    const sn = Math.min(spd / 42, 1);
                    const alpha = Math.min(profile.alphaMax, life * (profile.alphaSpeedScale + sn * 0.35));
                    const r = Math.round(120 + sn * 90);
                    const g = Math.round(170 + sn * 50);
                    const lw = profile.lineWidthBase + sn * profile.lineWidthSpeed;

                    ctx.beginPath();
                    ctx.moveTo(p.px, p.py);
                    ctx.lineTo(x, y);
                    ctx.strokeStyle = `rgba(${r},${g},248,${alpha.toFixed(2)})`;
                    ctx.lineWidth = lw;
                    ctx.lineCap = 'round';
                    ctx.stroke();
                }

                p.px = x;
                p.py = y;

                if (p.age >= p.max || x < -20 || x > cssW + 20 || y < -20 || y > cssH + 20) {
                    Object.assign(p, spawnOne(m, profile.maxAge));
                }
            }
        };

        const onMove = () => resetTrails();

        const ro = new ResizeObserver(() => resize());
        if (canvas.parentElement) ro.observe(canvas.parentElement);

        lastZoomRef.current = map.getZoom();
        resize();
        syncParticleCount(map, streamProfile(lastZoomRef.current).particleCount, streamProfile(lastZoomRef.current).maxAge);
        rafRef.current = requestAnimationFrame(frame);

        map.on('move', onMove);
        map.on('resize', resize);
        window.addEventListener('resize', resize);

        return () => {
            running = false;
            cancelAnimationFrame(rafRef.current);
            ro.disconnect();
            map.off('move', onMove);
            map.off('resize', resize);
            window.removeEventListener('resize', resize);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };
    }, [mapRef, mapReady, active, windField]);

    if (!active) return null;

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
                zIndex: 3,
            }}
        />
    );
}
