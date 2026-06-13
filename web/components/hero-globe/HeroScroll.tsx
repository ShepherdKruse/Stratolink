/**
 * Scroll-driven landing hero.
 *
 * A tall (300vh) section with a pinned 100vh stage. As you scroll:
 *   Phase A  — "STRATOLINK" wordmark large, the picoballoon floating below it.
 *   Phase B  — the globe rises from the bottom; the balloon shrinks and drifts
 *              down toward the globe's centre (the launch anchor).
 *   Phase C  — the balloon crossfades into the Mapbox dot on the globe surface;
 *              the tagline + "Launch a balloon" CTA resolve in. Once "docked",
 *              HeroGlobe auto-launches the anchor balloon and traces its flight.
 *
 * The "Launch a balloon" button launches another real simulated trajectory
 * (colour-coded); completed flights stay drawn, so a small fleet accumulates.
 *
 * The heavy WebGL camera is NOT scroll-driven (that janks); the globe <div> is
 * translated up with a compositor-cheap CSS transform for the "rises from the
 * bottom" effect, and the balloon simply converges on the stage centre, where
 * the globe's anchor projects. prefers-reduced-motion gets a static, un-pinned
 * version with a launched path already drawn.
 */
'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { motion, useScroll, useTransform, useMotionValueEvent, useMotionTemplate, useReducedMotion } from 'framer-motion';
import HeroGlobe from './HeroGlobe';
import { PerfHud } from './PerfHud';

/* The globe is rendered into a large SQUARE canvas so the whole sphere + its
 * atmosphere exist at the biggest size; scroll then CSS-scales it down (crisp,
 * never upscaled) and lifts it. The sphere is GLOBE_FILL of the square, leaving
 * a margin for the atmosphere glow to fade out (so neither the sphere nor the
 * glow gets clipped by the square's edges). */
const GLOBE_VH = 180;                 /* canvas square side, in vh */
const GLOBE_FILL = 0.6;               /* sphere = this fraction of the canvas — MUST match HeroGlobe */
const HEADER_VH = 8;                  /* sticky nav height (~80px); the docked globe sits below it */
const BOTTOM_GAP = 32;                /* total vertical slack around the docked sphere (split evenly top/bottom once centred) — keeps its atmosphere halo off both edges. Bigger = smaller globe + more clearance; smaller = bigger globe + tighter. */
const DOCK_DIAM = 100 - HEADER_VH - BOTTOM_GAP;   /* docked sphere diameter (vh) */
const CAP_TOP = 80;                   /* vh of the sphere's top edge at load — only the cap below shows */
const GLOBE_SETTLE = 0.6;             /* scroll fraction by which it's docked; the rest is a long tail */

/* Derived transform endpoints (sphere is centred in the square, so its centre
 * sits at GLOBE_VH/2 within the unscaled square). */
const BASE_DIAM = GLOBE_VH * GLOBE_FILL;             /* sphere diameter at scale 1 */
const GLOBE_END_SCALE = DOCK_DIAM / BASE_DIAM;       /* scale so the sphere = DOCK_DIAM */
/* Vertical centre of the region BELOW the menu bar — midpoint of [HEADER_VH, 100],
 * NOT the full-screen centre — so the docked sphere sits centred between the menu
 * bar's bottom edge and the window's bottom edge (equal slack above and below). */
const DOCK_CENTER_Y = HEADER_VH + (100 - HEADER_VH) / 2;
const GLOBE_END_Y = DOCK_CENTER_Y - (GLOBE_VH / 2) * GLOBE_END_SCALE;
const GLOBE_START_Y = CAP_TOP - (GLOBE_VH * (1 - GLOBE_FILL)) / 2;

const TAGLINE = 'A distributed network of pico-balloons mapping the stratosphere';

/* Shared caption + CTAs for the resolved hero. */
function HeroLockup({ onLaunch, launches }: { onLaunch: () => void; launches: number }) {
    return (
        <div className="flex flex-col items-center text-center">
            <p className="max-w-md text-pretty text-base font-light leading-relaxed text-slate-600 sm:text-lg">
                {TAGLINE}
            </p>
            <div className="mt-6 flex flex-col items-center gap-3">
                <button
                    type="button"
                    onClick={onLaunch}
                    className="rounded-sm bg-primary px-7 py-3 font-mono text-xs font-medium uppercase tracking-[0.12em] text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
                >
                    {launches === 0 ? 'Launch a balloon' : 'Launch another balloon'}
                </button>
                <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1">
                    <Link href="#contact" className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline">
                        Request access
                    </Link>
                    <Link href="/dashboard" className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline">
                        Open Mission Control
                    </Link>
                </div>
            </div>
        </div>
    );
}

export function HeroScroll() {
    const reduce = useReducedMotion();
    return reduce ? <ReducedHero /> : <HeroScrollAnimated />;
}

/* Static, un-pinned fallback — globe docked with a path pre-drawn. */
function ReducedHero() {
    const [launches, setLaunches] = useState(0);
    return (
        <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden border-b bg-background px-6 py-24">
            <div className="absolute inset-x-0 bottom-0 top-1/3">
                <HeroGlobe docked reducedMotion launchNonce={launches} />
            </div>
            <div className="relative z-10 flex flex-col items-center">
                <h1 className="text-5xl font-semibold tracking-tight text-slate-900 sm:text-7xl">STRATOLINK</h1>
                <div className="mt-8">
                    <HeroLockup onLaunch={() => setLaunches((n) => n + 1)} launches={launches} />
                </div>
            </div>
        </section>
    );
}

function HeroScrollAnimated() {
    const scrollRef = useRef<HTMLElement>(null);
    /* `?dock=1` starts docked (globe animating immediately, no scroll) — a dev/
     * perf aid so the animating hot path can be profiled directly. Harmless. */
    const [docked, setDocked] = useState(
        () => typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('dock'),
    );
    const [launches, setLaunches] = useState(0);

    const { scrollYProgress } = useScroll({
        target: scrollRef,
        offset: ['start start', 'end end'],
    });

    /* Latch docked once the globe has settled to full-page; don't un-dock on
     * scroll-up (the globe slides back off-screen up top anyway). */
    useMotionValueEvent(scrollYProgress, 'change', (v) => {
        if (v >= GLOBE_SETTLE && !docked) setDocked(true);
    });

    /* Globe: starts bigger than the screen, pushed down so only its top cap
     * shows; as you scroll it shrinks (scale 1 → fills height) and rises to
     * centre. Pure CSS transform on the big square — crisp, compositor-cheap. */
    const globeScale = useTransform(scrollYProgress, [0, GLOBE_SETTLE], [1, GLOBE_END_SCALE]);
    const globeTY = useTransform(scrollYProgress, [0, GLOBE_SETTLE], [`${GLOBE_START_Y}vh`, `${GLOBE_END_Y}vh`]);
    const globeTransform = useMotionTemplate`translateX(-50%) translateY(${globeTY}) scale(${globeScale})`;

    /* Big wordmark: lifts and fades out as the globe grows. */
    const wordmarkY = useTransform(scrollYProgress, [0.1, 0.45], ['0vh', '-14vh']);
    const wordmarkOpacity = useTransform(scrollYProgress, [0.12, 0.4], [1, 0]);

    /* Balloon graphic: floats at the top and simply fades out as you scroll. */
    const balloonOpacity = useTransform(scrollYProgress, [0.05, 0.4], [1, 0]);

    /* Resolved tagline + CTAs fade in once the globe is full-page. */
    const lockupOpacity = useTransform(scrollYProgress, [GLOBE_SETTLE, GLOBE_SETTLE + 0.12], [0, 1]);
    const lockupY = useTransform(scrollYProgress, [GLOBE_SETTLE, GLOBE_SETTLE + 0.12], ['1.5rem', '0rem']);

    /* Scroll cue, only while at the very top. */
    const cueOpacity = useTransform(scrollYProgress, [0, 0.06], [1, 0]);

    return (
        <section ref={scrollRef} className="relative h-[400vh] bg-background">
            <PerfHud />
            <div className="sticky top-0 h-screen overflow-hidden">
                {/* Globe layer — a large square (so the whole sphere exists),
                  * scaled down + lifted on scroll. Anchored top-centre. */}
                <motion.div
                    style={{
                        position: 'absolute',
                        top: 0,
                        left: '50%',
                        width: `${GLOBE_VH}vh`,
                        height: `${GLOBE_VH}vh`,
                        transformOrigin: '50% 0%',
                        transform: globeTransform,
                        /* Promote to its own compositor layer so the scroll-driven
                         * scale/translate composites in isolation — it never
                         * repaints the wordmark/balloon/CTA stacked over it. */
                        willChange: 'transform',
                    }}
                >
                    <HeroGlobe docked={docked} launchNonce={launches} scroll={scrollYProgress} settle={GLOBE_SETTLE} />
                </motion.div>

                {/* Big wordmark. */}
                <motion.h1
                    style={{ y: wordmarkY, opacity: wordmarkOpacity }}
                    className="pointer-events-none absolute inset-x-0 top-[20%] z-20 text-center text-6xl font-semibold tracking-tight text-slate-900 sm:text-8xl"
                >
                    STRATOLINK
                </motion.h1>

                {/* Balloon graphic — floats at the top, then simply fades as you
                  * scroll into the globe. */}
                <motion.div
                    style={{ opacity: balloonOpacity }}
                    className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center"
                >
                    <motion.div
                        /* Organic float — vertical, horizontal and rotational
                         * sways at different (non-harmonic) periods so the loop
                         * never reads as a rigid up-down. */
                        animate={{ y: [0, -16, 0], x: [0, 6, 0], rotate: [-1.4, 1.4, -1.4] }}
                        transition={{
                            y: { duration: 7, repeat: Infinity, ease: 'easeInOut' },
                            x: { duration: 9, repeat: Infinity, ease: 'easeInOut' },
                            rotate: { duration: 11, repeat: Infinity, ease: 'easeInOut' },
                        }}
                        style={{ willChange: 'transform' }}
                    >
                        <Image
                            src="/picoballoon.png"
                            alt="Stratolink pico-balloon"
                            width={600}
                            height={600}
                            priority
                            className="h-[20vh] w-auto drop-shadow-xl"
                        />
                    </motion.div>
                </motion.div>

                {/* Resolved tagline + CTAs. pointer-events follow opacity so the
                  * button isn't clickable until it's actually visible. */}
                <motion.div
                    style={{ opacity: lockupOpacity, y: lockupY }}
                    className="absolute inset-x-0 bottom-[8%] z-20 flex justify-center px-6"
                >
                    {docked && <HeroLockup onLaunch={() => setLaunches((n) => n + 1)} launches={launches} />}
                </motion.div>

                {/* Scroll cue. */}
                <motion.div
                    style={{ opacity: cueOpacity }}
                    className="pointer-events-none absolute inset-x-0 bottom-8 z-20 flex flex-col items-center gap-2 text-slate-400"
                >
                    <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em]">Scroll</span>
                    <span className="h-8 w-px bg-slate-300" />
                </motion.div>
            </div>
        </section>
    );
}
