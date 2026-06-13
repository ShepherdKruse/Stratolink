/**
 * Tiny frame-time profiler for the hero globe. Enable by adding `?fps` to the
 * URL. Measures requestAnimationFrame deltas and reports rolling FPS, the worst
 * frame in the last window, and cumulative counts of dropped (>18ms, i.e. below
 * ~55fps) and janky (>33ms) frames — so you can see whether scrolling the globe
 * or the docked animation is dropping frames.
 *
 * Dev-only: renders nothing unless `?fps` is present. The readout also lives in
 * a #perf-hud element so it can be read headlessly.
 */
'use client';

import { useEffect, useState } from 'react';

const DROP_MS = 1000 / 55; /* ~18.2ms — slower than this dropped below 55fps */
const JANK_MS = 1000 / 30; /* ~33ms — a clearly visible hitch */

export function PerfHud() {
    const [on, setOn] = useState(false);
    const [text, setText] = useState('measuring…');

    useEffect(() => {
        if (typeof window === 'undefined') return;
        if (!new URLSearchParams(window.location.search).has('fps')) return;
        setOn(true);

        let raf = 0;
        let last = performance.now();
        let frames = 0;
        let acc = 0;
        let worst = 0;
        let dropped = 0;
        let jank = 0;

        const tick = (now: number) => {
            const dt = now - last;
            last = now;
            frames++;
            acc += dt;
            if (dt > worst) worst = dt;
            if (dt > DROP_MS) dropped++;
            if (dt > JANK_MS) jank++;
            if (acc >= 500) {
                const fps = Math.round((frames * 1000) / acc);
                setText(`${fps} fps · worst ${worst.toFixed(0)}ms · drops ${dropped} · jank ${jank}`);
                frames = 0;
                acc = 0;
                worst = 0;
            }
            raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(raf);
    }, []);

    if (!on) return null;
    return (
        <div
            id="perf-hud"
            style={{
                position: 'fixed',
                top: 8,
                right: 8,
                zIndex: 9999,
                padding: '6px 10px',
                borderRadius: 4,
                background: 'rgba(10,14,22,0.85)',
                color: '#9feaff',
                font: '600 11px/1.3 ui-monospace, Menlo, monospace',
                letterSpacing: '0.02em',
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
            }}
        >
            {text}
        </div>
    );
}
