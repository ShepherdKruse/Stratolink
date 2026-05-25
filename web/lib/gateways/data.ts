/**
 * Shared loader for the ~14k ttnmapper gateway points (`/ttnmapper-gateways.json`).
 *
 * Used by the balloon-centered range view (rings + nearest-gateway readout).
 * Module-level memo + in-flight promise so every consumer shares one fetch;
 * the browser also caches the static file. Kept separate from GatewayLayer's
 * own memo so the proven ambient-coverage layer is untouched.
 */
'use client';

import { useEffect, useState } from 'react';
import type { GatewayPoint } from './range';

let cached: GatewayPoint[] | null = null;
let inFlight: Promise<GatewayPoint[]> | null = null;

export async function loadGatewayPoints(): Promise<GatewayPoint[]> {
    if (cached) return cached;
    if (inFlight) return inFlight;
    inFlight = (async () => {
        try {
            const r = await fetch('/ttnmapper-gateways.json');
            if (!r.ok) return [];
            const body = (await r.json()) as { gateways?: Array<{ lat: number; lon: number }> };
            cached = (body.gateways ?? []).map((g) => ({ lat: g.lat, lon: g.lon }));
            return cached;
        } catch {
            return [];
        } finally {
            inFlight = null;
        }
    })();
    return inFlight;
}

/** React hook wrapper — returns the gateway points once loaded ([] until then). */
export function useGatewayPoints(): GatewayPoint[] {
    const [points, setPoints] = useState<GatewayPoint[]>(cached ?? []);
    useEffect(() => {
        if (cached) {
            setPoints(cached);
            return;
        }
        let cancelled = false;
        loadGatewayPoints().then((pts) => {
            if (!cancelled) setPoints(pts);
        });
        return () => {
            cancelled = true;
        };
    }, []);
    return points;
}
