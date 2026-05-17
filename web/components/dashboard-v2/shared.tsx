/**
 * Shared hooks and small components used across all dashboard-v2 screens.
 */
'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';

/* Tick the wall clock every `intervalMs` so age labels stay current. */
export function useTickingNow(intervalMs = 1000): number {
    const [now, setNow] = useState<number>(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), intervalMs);
        return () => clearInterval(id);
    }, [intervalMs]);
    return now;
}

/* Observe an element's size so SVG charts can size to their container.
 * Returns a ref + the latest measured width/height. */
export function useElementSize(initialWidth = 600, initialHeight = 200): {
    ref: RefObject<HTMLDivElement | null>;
    width: number;
    height: number;
} {
    const ref = useRef<HTMLDivElement | null>(null);
    const [size, setSize] = useState({ width: initialWidth, height: initialHeight });
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        function update() {
            if (!el) return;
            const rect = el.getBoundingClientRect();
            setSize({
                width: Math.max(1, Math.round(rect.width)),
                height: Math.max(1, Math.round(rect.height)),
            });
        }
        update();
        const obs = new ResizeObserver(update);
        obs.observe(el);
        return () => obs.disconnect();
    }, []);
    return { ref, ...size };
}

/* Connection pill — small status badge for the top chrome. */
export function ConnectionPill({ status, lastFetchedAt, now }: {
    status: 'connecting' | 'connected' | 'disconnected' | 'error';
    lastFetchedAt: number | null;
    now: number;
}) {
    if (status === 'disconnected') {
        return <span className="sl-pill amber">SUPABASE NOT CONFIGURED</span>;
    }
    if (status === 'error') {
        return <span className="sl-pill amber">DATABASE ERROR</span>;
    }
    if (status === 'connecting' || lastFetchedAt === null) {
        return <span className="sl-pill dim">CONNECTING…</span>;
    }
    const ageS = Math.floor((now - lastFetchedAt) / 1000);
    return <span className="sl-pill teal">LIVE · POLL {ageS}s</span>;
}

/* Classic globe + mobile-shell dashboard (bookmark / debug). Primary UX is this v2 app. */
export function V1Link() {
    return (
        <a
            href="/dashboard"
            style={{
                fontSize: 10,
                letterSpacing: '0.10em',
                textTransform: 'uppercase',
                color: 'var(--sl-text-dim2)',
                textDecoration: 'none',
                border: '1px solid var(--sl-border-hi)',
                padding: '4px 8px',
            }}
        >
            ← classic
        </a>
    );
}

/* The firmware reports raw barometer counts that aren't scaled to mbar yet
 * (we saw ~3300 counts in production CSVs vs ~1013 mbar at sea level). Until
 * the firmware ships proper scaling, render the value as `dn` (digital
 * number) so the unit doesn't lie. */
export function fmtPressure(v: number | null): string {
    if (v === null || !Number.isFinite(v)) return '—';
    return `${v.toFixed(0)}dn`;
}
