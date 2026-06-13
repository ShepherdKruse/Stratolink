/**
 * Marketing hero globe — a clean, slowly turning Mapbox globe that launches and
 * traces real simulated balloon flights. Visually identical cartography to the
 * Mission Control dashboard (it reuses the SAME style helpers in
 * components/maps/, including the live day/night terminator), but with no
 * gateway coverage — a quiet relief globe for the landing page.
 *
 * It does NOT touch any dashboard-v2 code: the shared look comes from the
 * components/maps/ helpers (applyBaseStyle, bathymetryAllZooms,
 * quietBasemapLabels), which the dashboard also consumes.
 *
 * Trajectories are loaded from /balloon_trajectories.geojson (a slimmed copy of
 * the stratolink-simulation run: 20 balloons, 30 days, 15-min samples). Many
 * circle the globe 2–3×, so each is rendered as a short FADING COMET TRAIL that
 * follows the balloon — longitudes are rebased into the renderable range (a full
 * continuous line ran past Mapbox's world copies and vanished), and the tail
 * fades to transparent so old track clears instead of cluttering the globe.
 *
 * Behaviour:
 *  - Centres on the westernmost-launch balloon (a natural eastward sweep).
 *  - On `docked`, auto-launches that anchor balloon once.
 *  - Each `launchNonce` bump launches another balloon, coloured from a
 *    harmonious muted PALETTE (the sim's loud per-balloon hues are discarded).
 *  - The globe does NOT auto-rotate; after docking the user can drag to pan.
 *  - Per-flight trace duration scales with track length (longer flights take
 *    longer to draw).
 *  - `reducedMotion` / fallbacks draw launched trails complete, no animation.
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { applyBaseStyle } from '@/components/maps/baseStyle';
import { bathymetryAllZooms } from '@/components/maps/bathymetry';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';
import DayNightTerminator from '@/components/maps/DayNightTerminator';
import { simulatePath, loadWindSeries, seriesSpanHours, type WindSeries } from './windPath';
import type { MotionValue } from 'framer-motion';

type LngLat = [number, number];

interface Traj {
    id: string;
    color: string;
    /** Unwrapped (continuous-longitude) [lon, lat] track. */
    path: LngLat[];
    /** Trace duration (ms), scaled to a constant angular speed. */
    durationMs: number;
}

interface Flight {
    key: number;
    traj: Traj;
    startMs: number;
    headIdx: number;
    prog: number; /* 0→1 along the trace, for the end-fade */
    done: boolean;
}

/* Globe color scheme — flip to 'light' to revert. Drives the basemap, relief,
 * bathymetry and terminator together. */
const SCHEME = 'light' as 'light' | 'dark';
const MAP_STYLE = SCHEME === 'dark' ? 'mapbox://styles/mapbox/dark-v11' : 'mapbox://styles/mapbox/light-v11';
/* The globe fills its (square) container: HeroScroll renders the globe into a
 * large square and CSS-scales/translates it on scroll. We pick a zoom so the
 * sphere spans the container, then never touch the camera on scroll (CSS does
 * the size/position animation, which is crisp and compositor-cheap).
 *
 * Globe pixel diameter ≈ worldSize/π = 512·2^z/π. GLOBE_FILL keeps the sphere a
 * fraction of the square so there's a margin around it for the atmosphere glow
 * to fade out (and so the sphere's edges never touch / get clipped by the box).
 * MUST match GLOBE_FILL in HeroScroll (which sizes/positions the square). */
const GLOBE_ZOOM = 3.3;   /* initial fallback before the container is measured */
const GLOBE_FILL = 0.6;
const COVERAGE_KM = 250; /* per-balloon coverage radius drawn on the globe */
const DEG_PER_SEC = 17; /* eastward °/sec → per-flight trace duration (lower = slower) */
const MIN_TRACE_MS = 18000;
const MAX_TRACE_MS = 52000;
const TRAJ_URL = '/balloon_trajectories.geojson';
const WIND_URL = '/wind_300hpa_series.json';   /* 300 hPa wind time series for click-to-launch */
const FLIGHT_STEPS = 384;   /* 16 days at 1h/step */

/* Fixed terminator instant — chosen so the day/night line falls across the US
 * (eastern US in dusk/night, west still lit). June solstice → a tilted (slanted)
 * terminator rather than a vertical one; ~00:30 UTC puts the boundary near the
 * central US. We don't track real time for the hero, so this stays put. Nudge
 * the UTC hour to slide the line east/west; change the date to re-tilt it.
 * 2024-06-21T02:00Z = 7:00 PM Pacific (PDT, UTC−7) on the June solstice. */
const TERMINATOR_AT = Date.parse('2024-06-21T02:00:00Z');

/* Zoom so the sphere spans (≈ GLOBE_FILL ×) the container's short side. */
function fitZoom(w: number, h: number): number {
    const d = GLOBE_FILL * Math.min(w, h);
    return Math.log2(Math.max(1, (d * Math.PI) / 512));
}

/* End-of-flight fade: over the last (1 - FADE_START) of a track the balloon and
 * its trail fade out and the flight is removed. */
const FADE_START = 0.82;
function endFade(prog: number): number {
    return prog <= FADE_START ? 1 : Math.max(0, 1 - (prog - FADE_START) / (1 - FADE_START));
}

/* Harmonious, desaturated palette (cool-leaning with a couple of warm earth
 * tones) — replaces the simulation's loud per-balloon hues so the fleet reads
 * as a cohesive set against the quiet relief globe. Assigned by balloon index. */
const PALETTE = [
    '#4f7a8c', /* muted teal-blue   */
    '#7d8aa5', /* slate periwinkle  */
    '#6e9b8b', /* sage teal         */
    '#a8826d', /* soft terracotta   */
    '#8f7da6', /* dusty lavender    */
    '#c2a36b', /* muted ochre       */
    '#5f8d9c', /* steel cyan        */
    '#9c7f86', /* dusty rose        */
];

/* Comet-tail trail: only the most recent slice of each flight is drawn, fading
 * to transparent behind the balloon. Keeps the line in the renderable longitude
 * range (multi-circumnavigation tracks ran past Mapbox's world copies and
 * vanished) and reads as "fades over time". TRAIL_LEN is in path-index units
 * (15-min samples → 620 ≈ 6.5 days of flight). */
const TRAIL_LEN = 620;
const TRAIL_SAMPLES = 64; /* points kept before smoothing (fewer = cheaper per-frame parse) */
const TRAIL_SMOOTH_ITERS = 2; /* Chaikin passes — higher = smoother but more vertices */

function isWebGLAvailable(): boolean {
    if (typeof window === 'undefined') return false;
    try {
        const canvas = document.createElement('canvas');
        return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
    } catch {
        return false;
    }
}

/** Continuous (unwrapped) longitude → folded into [-180, 180] for display. */
function fold(lon: number): number {
    return (((lon + 180) % 360) + 360) % 360 - 180;
}

/** Unwrap a folded track so consecutive points never jump ~360°. */
function unwrap(coords: LngLat[]): LngLat[] {
    if (coords.length < 2) return coords.map((p) => [...p] as LngLat);
    const out: LngLat[] = [[...coords[0]] as LngLat];
    let prev = coords[0][0];
    for (let i = 1; i < coords.length; i++) {
        let lon = coords[i][0];
        while (lon - prev > 180) lon -= 360;
        while (lon - prev < -180) lon += 360;
        out.push([lon, coords[i][1]]);
        prev = lon;
    }
    return out;
}

/** Linearly-interpolated point at a fractional index, so a flight's dot and the
 *  leading edge of its line share one exact position (no lead/lag). */
function pointAt(path: LngLat[], idx: number): LngLat {
    const last = path.length - 1;
    const i = Math.max(0, Math.min(last, Math.floor(idx)));
    const a = path[i];
    const b = path[Math.min(last, i + 1)];
    const f = idx - i;
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

/** Geodesic circle (ring of [lon,lat]) of `km` radius around a centre, with
 *  longitudes kept continuous relative to the centre so it doesn't tear. */
function circleRing(lon: number, lat: number, km: number, steps = 48): LngLat[] {
    const R = 6371;
    const d = km / R;
    const latR = (lat * Math.PI) / 180;
    const lonR = (lon * Math.PI) / 180;
    const ring: LngLat[] = [];
    for (let i = 0; i <= steps; i++) {
        const brng = (i / steps) * 2 * Math.PI;
        const lat2 = Math.asin(Math.sin(latR) * Math.cos(d) + Math.cos(latR) * Math.sin(d) * Math.cos(brng));
        const lon2 = lonR + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(latR), Math.cos(d) - Math.sin(latR) * Math.sin(lat2));
        ring.push([(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
    }
    return ring;
}

function hexToRgba(hex: string, a: number): string {
    const h = hex.replace('#', '');
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/** Chaikin corner-cutting — smooths a polyline's kinks into a soft curve. */
function chaikin(pts: LngLat[], iterations: number): LngLat[] {
    let p = pts;
    for (let k = 0; k < iterations; k++) {
        if (p.length < 3) break;
        const out: LngLat[] = [p[0]];
        for (let i = 0; i < p.length - 1; i++) {
            const a = p[i];
            const b = p[i + 1];
            out.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25]);
            out.push([a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
        }
        out.push(p[p.length - 1]);
        p = out;
    }
    return p;
}

/** The trailing comet window ending at the interpolated head: the recent slice
 *  of the path, downsampled, longitude-rebased into the renderable range, then
 *  Chaikin-smoothed. Ordered oldest→head so line-progress 0 = faded tail. */
function trailCoords(path: LngLat[], headIdx: number): LngLat[] {
    const last = path.length - 1;
    const start = Math.max(0, headIdx - TRAIL_LEN);

    /* Sample interior points at a FIXED stride on ABSOLUTE path indices, not by
     * resampling the window each frame. As the window slides, the same indexed
     * vertices stay selected (the oldest just drops off the faded tail and a new
     * one appears near the head), so the curve is rock-steady instead of
     * shimmering. Only the two interpolated endpoints move, smoothly. */
    const stride = Math.max(1, Math.ceil(TRAIL_LEN / TRAIL_SAMPLES));
    const pts: LngLat[] = [pointAt(path, start)];
    const firstStride = Math.ceil(start / stride) * stride;
    for (let i = firstStride; i <= Math.floor(headIdx); i += stride) {
        if (i > start && i <= last) pts.push(path[i]);
    }
    const head = pointAt(path, headIdx);
    pts.push(head);
    if (pts.length < 2) return [];

    /* Rebase longitudes so the head folds into [-180,180]; the trail then stays
     * within a world copy Mapbox actually renders. Shifting by a multiple of
     * 360 is a no-op on the globe but keeps the numbers in range. */
    const shift = fold(head[0]) - head[0];
    const rebased = pts.map(([lo, la]) => [lo + shift, la] as LngLat);

    return chaikin(rebased, TRAIL_SMOOTH_ITERS);
}

/** Per-flight fading gradient (tail transparent → head solid), baked with the
 *  balloon's colour since line-gradient can't read feature properties. `scale`
 *  multiplies every alpha so the whole trail can fade out near a flight's end. */
function trailGradient(color: string, scale: number): unknown {
    return [
        'interpolate', ['linear'], ['line-progress'],
        0, hexToRgba(color, 0),
        0.35, hexToRgba(color, 0.16 * scale),
        1, hexToRgba(color, 0.95 * scale),
    ];
}

/** Where the globe settles at dock — centred on the continental US (so North
 *  America is framed, with the terminator falling across it). */
const DOCKED_CENTER = { lon: -98, lat: 39 };
/** Centre latitude at load — tilted back so the globe's top edge shows ~80°N
 *  (the pole is on the far side); scroll rotates it up to DOCKED_CENTER.lat. */
const START_LAT = 0;
/** Degrees of longitude the globe spins through as it scrolls in, ending at
 *  DOCKED_CENTER. */
const SPIN_DEG = 50;

/** Stable empty source data — the trail/dot/coverage sources mount with this and
 *  are then fed imperatively via setData (a stable ref means react-map-gl never
 *  overwrites our imperative data). */
const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] as unknown[] };

/** Render the globe at 1/RENDER_SCALE resolution and CSS-upscale it to the same
 *  on-screen size — fewer pixels per repaint at the cost of a softer globe.
 *  1 = full Retina (crisp); >1 trades sharpness for fill rate. The downscale
 *  didn't move the needle here, so we keep it crisp at 1. */
const RENDER_SCALE = 1;

interface HeroGlobeProps {
    /** Once true, the anchor balloon auto-launches. */
    docked: boolean;
    /** Bumping this launches another (random) balloon. */
    launchNonce?: number;
    /** Draw launched paths complete, no animation (reduced-motion / fallback). */
    reducedMotion?: boolean;
    /** Fired once the map has loaded and the custom basemap is applied. */
    onReady?: () => void;
    /** Scroll progress (0→1) of the hero section; drives the spin-in. */
    scroll?: MotionValue<number>;
    /** Scroll fraction by which the globe is settled/centred (= GLOBE_SETTLE). */
    settle?: number;
}

export default function HeroGlobe({ docked, launchNonce = 0, reducedMotion = false, onReady, scroll, settle = 0.6 }: HeroGlobeProps) {
    const mapRef = useRef<MapRef>(null);
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);
    const [trajLoaded, setTrajLoaded] = useState(false);
    /* The set of live flights, as {key,color}. Changes only when a balloon
     * launches or lands — so React renders a stable set of Sources/Layers, and
     * the per-frame motion updates them IMPERATIVELY (setData) without any
     * per-frame React render. */
    const [flightList, setFlightList] = useState<{ key: number; color: string }[]>([]);
    /* Hidden until the map has loaded, fit, and settled — then fade in once, so
     * the load/fit camera settling isn't seen as a jump. */
    const [revealed, setRevealed] = useState(false);
    /* The day/night terminator is shown only while the globe is settled in place
     * (scroll past `settle`). Unlike `docked` (which latches), this tracks scroll
     * BOTH ways, so the terminator resolves in once the spin-in finishes and
     * disappears again if you scroll back up into the animation. */
    const [terminatorOn, setTerminatorOn] = useState(false);

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    const styledRef = useRef(false);

    /* Loaded trajectories + the anchor (westernmost launch). */
    const trajRef = useRef<Traj[]>([]);
    const anchorRef = useRef<Traj | null>(null);
    /* Pool of not-yet-launched ids; refills when exhausted. */
    const poolRef = useRef<string[]>([]);

    const flightsRef = useRef<Flight[]>([]);
    const keyRef = useRef(0);
    const rafRef = useRef<number | null>(null);
    /* Latest docked flag + launch fn, read inside the rAF loop (which closes
     * over stale values otherwise) to respawn an ambient balloon. */
    const dockedRef = useRef(docked);
    const launchRef = useRef<(specificId?: string) => void>(() => {});
    dockedRef.current = docked;
    /* The animation only runs while the globe is on-screen AND the tab is
     * visible — otherwise it idles (no rAF, no Mapbox repaints) to save CPU. */
    const rootRef = useRef<HTMLDivElement>(null);
    const [active, setActive] = useState(true);
    const activeRef = useRef(true);
    activeRef.current = active;
    const lastTickRef = useRef(0);
    /* Zoom that makes the sphere fill the (square) container — set on load and
     * resize. Scroll only CSS-transforms the container, never the camera. */
    const fitZoomRef = useRef(GLOBE_ZOOM);

    useEffect(() => { setWebglOk(isWebGLAvailable()); }, []);

    /* Load + parse the trajectories once. */
    useEffect(() => {
        let cancelled = false;
        fetch(TRAJ_URL)
            .then((r) => r.json())
            .then((fc) => {
                if (cancelled) return;
                const trajs: Traj[] = (fc.features ?? []).map((f: { properties: { balloon_id: string }; geometry: { coordinates: LngLat[] } }, i: number) => {
                    const path = unwrap(f.geometry.coordinates);
                    const span = Math.abs(path[path.length - 1][0] - path[0][0]);
                    const durationMs = Math.max(MIN_TRACE_MS, Math.min(MAX_TRACE_MS, (span / DEG_PER_SEC) * 1000));
                    /* Override the sim's loud hue with the harmonious palette. */
                    return { id: f.properties.balloon_id, color: PALETTE[i % PALETTE.length], path, durationMs };
                }).filter((t: Traj) => t.path.length >= 2);
                if (!trajs.length) return;
                /* Anchor = westernmost launch → a sweeping eastward hero flight. */
                const anchor = trajs.reduce((w, t) => (t.path[0][0] < w.path[0][0] ? t : w), trajs[0]);
                trajRef.current = trajs;
                anchorRef.current = anchor;
                poolRef.current = trajs.map((t) => t.id).filter((id) => id !== anchor.id);
                setTrajLoaded(true);
            })
            .catch(() => { /* fallback handles a missing/blocked file */ });
        return () => { cancelled = true; };
    }, []);

    /* Apply the shared dashboard cartography once the style is up. */
    const applyCustomStyle = useCallback(() => {
        const m = mapRef.current?.getMap();
        if (!m || styledRef.current) return;
        try {
            /* A little atmosphere — a soft halo at the globe's limb. `space-color`
             * matches the page so the rim fades into it rather than a hard edge. */
            m.setFog((SCHEME === 'dark'
                ? { range: [1, 10], 'horizon-blend': 0.02, color: '#0b1622', 'high-color': '#16314d', 'space-color': '#0a0e16', 'star-intensity': 0.06 }
                : { range: [1, 10], 'horizon-blend': 0.02, color: '#eef4fb', 'high-color': '#d3e1f1', 'space-color': '#ffffff', 'star-intensity': 0 }) as never);
            quietBasemapLabels(m);
            applyBaseStyle(m, SCHEME);
            bathymetryAllZooms(m, SCHEME);
            /* Pure white around the globe to match the (pure-white) page. White
             * (255,255,255) is the one colour that renders identically in WebGL
             * and CSS, so the canvas and page whites match exactly — no seam. */
            if (m.getLayer('background')) {
                m.setPaintProperty('background', 'background-color', '#ffffff');
                m.setPaintProperty('background', 'background-opacity', 1);
            }
            /* (Polar cap is handled in the shared bathymetryAllZooms — small cap
             * at the pole, blended tone.) */
            styledRef.current = true;
            onReady?.();
        } catch { /* style mid-load; a later styledata retries */ }
    }, [onReady]);

    /* Size the sphere to fill the (square) container; re-fit on resize. */
    const applyFit = useCallback(() => {
        const m = mapRef.current?.getMap();
        if (!m) return;
        const c = m.getContainer(); // the (downscaled) canvas container
        const z = fitZoom(c.offsetWidth, c.offsetHeight);
        fitZoomRef.current = z;
        try { m.setZoom(z); } catch { /* ignore */ }
    }, []);

    useEffect(() => {
        const onResize = () => applyFit();
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, [applyFit]);

    /* Safety net: reveal even if `idle` is slow (poor connection), so the globe
     * can never stay hidden. */
    useEffect(() => {
        if (!styleLoaded || revealed) return;
        const id = setTimeout(() => setRevealed(true), 2500);
        return () => clearTimeout(id);
    }, [styleLoaded, revealed]);

    /* Spin-in: drive the globe's centre longitude AND latitude from scroll, so
     * the earth rotates into place — starting tilted back (top ≈ 80°N) and
     * rotating up + east to the docked US centre at the settle point.
     *
     * Smoothing: scroll updates a TARGET; a small rAF eases the actual
     * orientation toward it, so coarse/steppy scroll events become fluid motion
     * (and it glides to rest when you stop). The loop idles when caught up, and
     * skips updates whose orientation is unchanged (the docked tail / panning),
     * so it neither repaints for nothing nor fights a manual pan. */
    useEffect(() => {
        const m = mapRef.current?.getMap();
        if (!m || !styleLoaded) return;
        const { lon: endLon, lat: endLat } = DOCKED_CENTER;
        const centerFor = (p: number): [number, number] => {
            const factor = Math.max(0, Math.min(1, 1 - p / settle));
            return [endLon - SPIN_DEG * factor, endLat + (START_LAT - endLat) * factor];
        };
        if (!scroll) { // no scroll driver (e.g. reduced-motion): just centre on the US
            try { m.jumpTo({ center: [fold(endLon), endLat], zoom: fitZoomRef.current }); } catch { /* ignore */ }
            return;
        }
        const DRAW_MS = 1000 / 40;   // cap the (heavy) camera repaint to ~40fps
        let target = scroll.get();
        let cur = target;        // start already at the target — no opening lurch
        let raf = 0;
        let lastDraw = 0;
        let lastLon = NaN;
        let lastLat = NaN;
        const draw = () => {
            const [lon, lat] = centerFor(cur);
            if (lon === lastLon && lat === lastLat) return; // unchanged → don't fight pan / repaint
            lastLon = lon; lastLat = lat;
            try { m.jumpTo({ center: [fold(lon), lat], zoom: fitZoomRef.current }); } catch { /* ignore */ }
        };
        const tick = (now: number) => {
            cur += (target - cur) * 0.18;            // ease toward the scroll target
            const done = Math.abs(target - cur) < 0.0004;
            if (done) cur = target;
            if (done || now - lastDraw >= DRAW_MS) { lastDraw = now; draw(); }
            raf = done ? 0 : requestAnimationFrame(tick);
        };
        draw(); // initial orientation
        const unsub = scroll.on('change', (v) => {
            target = v;
            if (!raf) raf = requestAnimationFrame(tick);
        });
        return () => { unsub(); if (raf) cancelAnimationFrame(raf); };
    }, [scroll, settle, styleLoaded]);

    /* Drive terminator visibility from the live scroll position (both ways). No
     * scroll driver (reduced-motion / static fallback) → follow `docked`. */
    useEffect(() => {
        if (!scroll) { setTerminatorOn(docked); return; }
        const update = (v: number) => setTerminatorOn(v >= settle);
        update(scroll.get());
        const unsub = scroll.on('change', update);
        return unsub;
    }, [scroll, settle, docked]);

    /* Imperatively push the current flight positions to Mapbox — no React render.
     * Trails: geometry via setData; the end-fade rides cheap `line-opacity` (the
     * tail-fade gradient stays static, so we never re-tessellate it per frame).
     * Dots + coverage: single sources with data-driven opacity. */
    const paintFlights = useCallback(() => {
        const m = mapRef.current?.getMap();
        if (!m) return;
        const flights = flightsRef.current;
        for (const f of flights) {
            const fade = reducedMotion ? 1 : endFade(f.prog);
            const src = m.getSource(`hero-trail-${f.key}`) as { setData?: (d: unknown) => void } | undefined;
            if (src?.setData) {
                const coords = trailCoords(f.traj.path, f.headIdx);
                src.setData(coords.length >= 2
                    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} }] }
                    : { type: 'FeatureCollection', features: [] });
            }
            if (m.getLayer(`hero-trail-line-${f.key}`)) {
                try { m.setPaintProperty(`hero-trail-line-${f.key}`, 'line-opacity', fade); } catch { /* ignore */ }
            }
        }
        const dots = m.getSource('hero-dots') as { setData?: (d: unknown) => void } | undefined;
        dots?.setData?.({
            type: 'FeatureCollection',
            features: flights.map((f) => {
                const [lon, lat] = pointAt(f.traj.path, f.headIdx);
                const fade = reducedMotion ? 1 : endFade(f.prog);
                return { type: 'Feature', geometry: { type: 'Point', coordinates: [fold(lon), lat] }, properties: { color: f.traj.color, opacity: fade, haloOpacity: 0.18 * fade } };
            }),
        });
        const cov = m.getSource('hero-coverage') as { setData?: (d: unknown) => void } | undefined;
        cov?.setData?.({
            type: 'FeatureCollection',
            features: flights.map((f) => {
                const [lon, lat] = pointAt(f.traj.path, f.headIdx);
                const fade = reducedMotion ? 1 : endFade(f.prog);
                return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [circleRing(fold(lon), lat, COVERAGE_KM)] }, properties: { color: f.traj.color, fillOpacity: 0.06 * fade, lineOpacity: 0.45 * fade } };
            }),
        });
    }, [reducedMotion]);

    const ensureLoop = useCallback(() => {
        if (rafRef.current != null) return;
        const FRAME_MS = 1000 / 30; /* throttle the (time-based) trace to ~30fps */
        const step = (now: number) => {
            /* Idle entirely when off-screen / tab hidden — resumed by the active
             * effect below. */
            if (!activeRef.current) { rafRef.current = null; return; }
            /* Throttle the heavy work (Chaikin trails + Mapbox setData + React
             * render) to ~30fps; positions are time-based so this doesn't alter
             * the motion. */
            if (now - lastTickRef.current < FRAME_MS) {
                rafRef.current = requestAnimationFrame(step);
                return;
            }
            lastTickRef.current = now;
            for (const f of flightsRef.current) {
                if (f.done) continue;
                const p = Math.min(1, (now - f.startMs) / f.traj.durationMs);
                const e = 0.5 - 0.5 * Math.cos(Math.PI * p); /* easeInOutSine */
                f.headIdx = e * (f.traj.path.length - 1);
                f.prog = p;
                if (p >= 1) f.done = true; /* faded out by now (see endFade) */
            }
            /* Drop finished flights — they fade and disappear at the end. Only
             * touch React state when the SET changes (a flight landed), so the
             * Source/Layer set is added/removed; per-frame motion is imperative. */
            const before = flightsRef.current.length;
            flightsRef.current = flightsRef.current.filter((f) => !f.done);
            if (flightsRef.current.length !== before) {
                setFlightList(flightsRef.current.map((f) => ({ key: f.key, color: f.traj.color })));
            }
            /* Keep the globe alive: when the last balloon lands, launch another. */
            if (flightsRef.current.length === 0 && dockedRef.current) {
                launchRef.current();
            }
            /* Push positions imperatively — no React render this frame. */
            paintFlights();
            if (flightsRef.current.some((f) => !f.done)) {
                rafRef.current = requestAnimationFrame(step);
            } else {
                rafRef.current = null;
            }
        };
        rafRef.current = requestAnimationFrame(step);
    }, [paintFlights]);

    /* Push a flight for a trajectory and start the loop (or, in reduced motion,
     * draw it complete). Shared by all launch entry points. */
    const startFlight = useCallback((traj: Traj) => {
        const key = keyRef.current++;
        flightsRef.current.push(reducedMotion
            ? { key, traj, startMs: 0, headIdx: traj.path.length - 1, prog: 1, done: false }
            : { key, traj, startMs: performance.now(), headIdx: 0, prog: 0, done: false });
        setFlightList((l) => [...l, { key, color: traj.color }]); // mounts this flight's Source/Layer
        if (!reducedMotion) ensureLoop(); // reduced-motion is painted once by the effect below
    }, [reducedMotion, ensureLoop]);

    /* Reduced motion (and the first paint after a launch): draw the current
     * positions once the flightList's Sources have mounted. */
    useEffect(() => {
        if (styleLoaded) paintFlights();
    }, [flightList, styleLoaded, paintFlights]);

    /* Launch a pre-baked balloon. `specificId` → the anchor auto-launch; none →
     * a random unlaunched balloon (pool refills when dry). */
    const launch = useCallback((specificId?: string) => {
        const trajs = trajRef.current;
        if (!trajs.length) return;
        let traj: Traj | undefined;
        if (specificId) {
            traj = trajs.find((t) => t.id === specificId);
        } else {
            if (poolRef.current.length === 0) poolRef.current = trajs.map((t) => t.id);
            const idx = Math.floor(Math.random() * poolRef.current.length);
            const id = poolRef.current.splice(idx, 1)[0];
            traj = trajs.find((t) => t.id === id);
        }
        if (traj) startFlight(traj);
    }, [startFlight]);

    /* Expose the latest launch fn to the rAF loop's respawn. */
    useEffect(() => { launchRef.current = launch; }, [launch]);

    /* Click-to-launch: integrate a realistic path from the clicked point through
     * the 300 hPa wind field and fly it. */
    const windRef = useRef<WindSeries | null>(null);
    useEffect(() => {
        let cancelled = false;
        loadWindSeries(WIND_URL)
            .then((w) => { if (!cancelled) windRef.current = w; })
            .catch(() => { /* click-launch just no-ops if the field is missing */ });
        return () => { cancelled = true; };
    }, []);

    const clickCountRef = useRef(0);
    const launchAt = useCallback((lon: number, lat: number) => {
        const w = windRef.current;
        if (!w) return;
        /* Random start time within the series (leaving room for the full flight),
         * so the same spot launched twice rides different, evolving winds. */
        const maxStart = Math.max(0, seriesSpanHours(w) - FLIGHT_STEPS);
        const startHour = Math.random() * maxStart;
        const path = simulatePath(w, lon, lat, { dtHours: 1, steps: FLIGHT_STEPS, startHour });
        if (path.length < 2) return;
        const span = Math.abs(path[path.length - 1][0] - path[0][0]);
        const durationMs = Math.max(MIN_TRACE_MS, Math.min(MAX_TRACE_MS, (span / DEG_PER_SEC) * 1000));
        const color = PALETTE[clickCountRef.current++ % PALETTE.length];
        startFlight({ id: `click-${clickCountRef.current}`, color, path, durationMs });
    }, [startFlight]);

    /* Auto-launch the anchor balloon once, on dock. */
    const autoLaunchedRef = useRef(false);
    useEffect(() => {
        if (!docked || !trajLoaded || autoLaunchedRef.current) return;
        autoLaunchedRef.current = true;
        launch(anchorRef.current?.id);
    }, [docked, trajLoaded, launch]);

    /* Button-driven launches. */
    useEffect(() => {
        if (launchNonce <= 0 || !trajLoaded) return;
        launch();
    }, [launchNonce, trajLoaded, launch]);

    useEffect(() => () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current); }, []);

    /* Track on-screen + tab-visibility → `active`. Off-screen or backgrounded,
     * the globe stops animating (the biggest CPU saver). Re-runs once the real
     * map div mounts (webglOk resolves) — on first render rootRef is still the
     * pre-check placeholder, so a []-effect would never attach the observer and
     * the globe would never pause. */
    useEffect(() => {
        const el = rootRef.current;
        if (!el) return;
        let onScreen = true;
        let shown = typeof document !== 'undefined' ? !document.hidden : true;
        const update = () => setActive(onScreen && shown);
        const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; update(); }, { threshold: 0 });
        io.observe(el);
        const onVis = () => { shown = !document.hidden; update(); };
        document.addEventListener('visibilitychange', onVis);
        return () => { io.disconnect(); document.removeEventListener('visibilitychange', onVis); };
    }, [webglOk]);

    /* Start/stop the loop with `active`: resume in-flight trails (or restart the
     * ambient launch) when it comes back on-screen; the step self-cancels when
     * inactive. */
    useEffect(() => {
        if (!active) {
            if (rafRef.current != null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
            return;
        }
        if (flightsRef.current.some((f) => !f.done)) ensureLoop();
        else if (docked && trajLoaded) launchRef.current();
    }, [active, docked, trajLoaded, ensureLoop]);

    if (webglOk === false || !token) {
        return (
            <div
                aria-hidden
                style={{
                    position: 'absolute', inset: 0,
                    background: 'radial-gradient(circle at 50% 55%, #eef3f7 0%, #dfe7ee 45%, transparent 70%)',
                }}
            />
        );
    }
    if (webglOk === null) {
        return <div aria-hidden style={{ position: 'absolute', inset: 0 }} />;
    }

    return (
        <div ref={rootRef} style={{ width: '100%', height: '100%', opacity: revealed ? 1 : 0, transition: 'opacity 100ms ease' }}>
        {/* Render at 1/RENDER_SCALE resolution, CSS-upscale to fill — fewer pixels
          * per repaint at the same on-screen size. */}
        <div style={{ width: `${100 / RENDER_SCALE}%`, height: `${100 / RENDER_SCALE}%`, transform: `scale(${RENDER_SCALE})`, transformOrigin: 'top left' }}>
        <Map
            ref={mapRef}
            mapboxAccessToken={token}
            initialViewState={{ longitude: DOCKED_CENTER.lon - SPIN_DEG, latitude: START_LAT, zoom: GLOBE_ZOOM }}
            style={{ width: '100%', height: '100%' }}
            mapStyle={MAP_STYLE}
            projection="globe"
            /* Pan/zoom only after docking, so drags don't fight the scroll
             * sequence. Wheel-zoom stays OFF so the mouse wheel scrolls the
             * page rather than zooming the globe. */
            dragPan={docked}
            dragRotate={docked}
            touchZoomRotate={docked}
            doubleClickZoom={docked}
            scrollZoom={false}
            touchPitch={false}
            keyboard={false}
            attributionControl={false}
            logoPosition="bottom-left"
            /* The basemap is effectively static (one fixed instant, no live
             * tiles streaming in steady state), so kill Mapbox's symbol/tile
             * crossfade work — it's pure per-frame cost with nothing to fade. */
            fadeDuration={0}
            /* Globe view touches few tiles; a small cache avoids holding (and
             * periodically revalidating) a big tile set we never revisit. */
            maxTileCacheSize={64}
            refreshExpiredTiles={false}
            /* Click anywhere (once docked) to launch a balloon from there, its
             * path integrated live through the 300 hPa wind field. */
            cursor={docked ? 'crosshair' : 'default'}
            onClick={(e) => { if (docked) launchAt(e.lngLat.lng, e.lngLat.lat); }}
            onLoad={() => {
                setStyleLoaded(true);
                applyCustomStyle();
                applyFit();
                /* Wait for tiles + camera to settle, then fade in once. */
                const m = mapRef.current?.getMap();
                if (m) m.once('idle', () => setRevealed(true));
                else setRevealed(true);
            }}
            onStyleData={() => { setStyleLoaded(true); applyCustomStyle(); }}
        >
            {styleLoaded && (
                <>
                    {/* Day/night terminator (city lights + night shade), matching
                      * the dashboard but pinned to a fixed instant so the boundary
                      * sits over the US. Rendered first so it dims only the
                      * basemap; trails and dots sit on top.
                      *
                      * Shown only while settled: `terminatorOn` tracks the scroll
                      * position BOTH ways, so the dusk line washes in slowly once
                      * the globe comes to rest and fades back out as you scroll up
                      * into the animation (driven through `scrubbing`, which fades
                      * opacity rather than popping the layer in/out). */}
                    <DayNightTerminator
                        colorScheme={SCHEME}
                        date={TERMINATOR_AT}
                        scrubbing={!terminatorOn}
                        gentleReveal
                        revealShadeMs={500}
                        revealLightsMs={500}
                        hideMs={500}
                    />

                    {/* 250 km coverage region per balloon — fed imperatively. */}
                    <Source id="hero-coverage" type="geojson" data={EMPTY_FC as never}>
                        <Layer
                            id="hero-coverage-fill"
                            type="fill"
                            paint={{ 'fill-color': ['get', 'color'], 'fill-opacity': ['get', 'fillOpacity'] }}
                        />
                        <Layer
                            id="hero-coverage-ring"
                            type="line"
                            paint={{ 'line-color': ['get', 'color'], 'line-opacity': ['get', 'lineOpacity'], 'line-width': 1 }}
                        />
                    </Source>

                    {/* Fading comet trail — one gradient line layer per flight.
                      * The tail-fade gradient is STATIC (colour baked per layer);
                      * the end-of-flight fade rides `line-opacity` (set imperatively
                      * so we never re-tessellate the gradient). lineMetrics enables
                      * the along-line gradient. The flight SET only changes on
                      * launch/land, so these mount/unmount rarely. */}
                    {flightList.map((f) => (
                        <Source key={f.key} id={`hero-trail-${f.key}`} type="geojson" lineMetrics data={EMPTY_FC as never}>
                            <Layer
                                id={`hero-trail-line-${f.key}`}
                                type="line"
                                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                paint={{
                                    'line-gradient': trailGradient(f.color, 1) as never,
                                    'line-opacity': 1,
                                    'line-width': ['interpolate', ['linear'], ['zoom'], 2, 1.8, 5, 3],
                                }}
                            />
                        </Source>
                    ))}
                    <Source id="hero-dots" type="geojson" data={EMPTY_FC as never}>
                        <Layer
                            id="hero-dot-halo"
                            type="circle"
                            paint={{ 'circle-color': ['get', 'color'], 'circle-opacity': ['get', 'haloOpacity'], 'circle-radius': 12, 'circle-blur': 0.6 }}
                        />
                        <Layer
                            id="hero-dot-core"
                            type="circle"
                            paint={{
                                'circle-color': ['get', 'color'],
                                'circle-opacity': ['get', 'opacity'],
                                'circle-radius': 5,
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#ffffff',
                                'circle-stroke-opacity': ['get', 'opacity'],
                            }}
                        />
                    </Source>
                </>
            )}
        </Map>
        </div>
        </div>
    );
}
