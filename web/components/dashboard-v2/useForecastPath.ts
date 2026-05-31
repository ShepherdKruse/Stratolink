/**
 * useForecastPath — the balloon's predicted next track for the map.
 *
 * Reads the pre-computed Monte-Carlo forecast for a device from
 * `/api/forecast` (Vercel Blob, refreshed by cron; computed on demand when
 * none is cached) and returns the pieces the map draws: the nominal path,
 * the ensemble spaghetti, and the 50/90% confidence ellipses.
 *
 * Returns empty arrays (never throws) when no forecast exists yet, so the
 * map's forecast layers simply don't render.
 */
'use client';

import { useEffect, useState } from 'react';

/** [lon, lat] pairs, forecast origin → predicted endpoint. */
export type ForecastPath = Array<[number, number]>;

/** One time-slice cone: the 50% and 90% confidence rings as polygons. */
export interface ForecastEllipse {
    e50: Array<[number, number]>;
    e90: Array<[number, number]>;
}

/** A reconstructed hindcast point carrying its real (wind-interpolated) time.
 *  Same geometry as `hindcastPath`, but timestamps are anchored to the actual
 *  GPS-fix times rather than spaced evenly by index. */
export interface HindcastTrackPoint {
    lon: number;
    lat: number;
    /** Epoch ms. */
    t: number;
}

export interface UseForecastPathResult {
    /** Nominal predicted path ([lon, lat]). Empty until a forecast loads. */
    path: ForecastPath;
    /** Monte-Carlo ensemble members, each a [lon, lat] track. */
    ensemble: ForecastPath[];
    /** Per-slice 50/90% confidence ellipse polygons. */
    ellipses: ForecastEllipse[];
    /** Wind-reconstructed likely prior path through GPS gaps ([lon, lat]). */
    hindcastPath: ForecastPath;
    /** Same path as `hindcastPath`, but with a real timestamp per point — used
     *  to position the scrubbed balloon marker in sync with the transmit dots.
     *  Empty for forecasts computed before this field existed. */
    hindcastTrack: HindcastTrackPoint[];
    /** True when the last GPS fix is stale and the origin is dead-reckoned. */
    staleGps: boolean;
    /** Epoch ms of the forecast origin (path[0]'s time). Null if unknown. */
    originT: number | null;
    /** Epoch ms of the forecast horizon end (path's last point). */
    endT: number | null;
    /** ISO timestamp the forecast was generated, or null. */
    generatedAt: string | null;
    loading: boolean;
}

/* Re-poll occasionally so a freshly-computed forecast appears without a reload.
 * The stored forecast only changes on the cron cadence, so this is gentle. */
const POLL_MS = 5 * 60 * 1000;

const EMPTY: Omit<UseForecastPathResult, 'loading'> = {
    path: [], ensemble: [], ellipses: [], hindcastPath: [], hindcastTrack: [],
    staleGps: false, originT: null, endT: null, generatedAt: null,
};

/** Keep only well-formed [lon, lat] pairs in WGS84 range. */
function cleanPath(raw: unknown): ForecastPath {
    if (!Array.isArray(raw)) return [];
    return raw.filter(
        (p: unknown): p is [number, number] =>
            Array.isArray(p) && p.length === 2 &&
            Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
            Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90,
    );
}

/** Parse the timed reconstructed track ({ lon, lat, time_utc }) into points
 *  with epoch-ms timestamps, dropping anything malformed. */
function cleanTrack(raw: unknown): HindcastTrackPoint[] {
    if (!Array.isArray(raw)) return [];
    const out: HindcastTrackPoint[] = [];
    for (const p of raw as Array<{ lon?: unknown; lat?: unknown; time_utc?: unknown }>) {
        if (!p || typeof p !== 'object') continue;
        const { lon, lat } = p;
        const t = typeof p.time_utc === 'string' ? Date.parse(p.time_utc) : NaN;
        if (
            typeof lon === 'number' && typeof lat === 'number' &&
            Number.isFinite(lon) && Number.isFinite(lat) &&
            Math.abs(lon) <= 180 && Math.abs(lat) <= 90 && Number.isFinite(t)
        ) {
            out.push({ lon, lat, t });
        }
    }
    return out;
}

export function useForecastPath(deviceId: string | null): UseForecastPathResult {
    const [state, setState] = useState(EMPTY);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!deviceId) {
            setState(EMPTY);
            return;
        }
        let cancelled = false;
        setLoading(true);

        async function load() {
            try {
                const res = await fetch(`/api/forecast?device=${encodeURIComponent(deviceId!)}`);
                if (!res.ok) {
                    /* 404 = no forecast available. Treat as "nothing to draw". */
                    if (!cancelled) setState(EMPTY);
                    return;
                }
                const data = await res.json();
                if (cancelled) return;

                const path = cleanPath(data?.nominal_path);
                const ensemble: ForecastPath[] = Array.isArray(data?.ensemble)
                    ? data.ensemble.map(cleanPath).filter((t: ForecastPath) => t.length >= 2)
                    : [];
                const ellipses: ForecastEllipse[] = Array.isArray(data?.ellipses)
                    ? data.ellipses
                        .map((e: { e50?: { polygon?: unknown }; e90?: { polygon?: unknown } }) => ({
                            e50: cleanPath(e?.e50?.polygon),
                            e90: cleanPath(e?.e90?.polygon),
                        }))
                        .filter((e: ForecastEllipse) => e.e50.length >= 3 || e.e90.length >= 3)
                    : [];

                /* Future-scrub window: path[0] sits at the forecast origin time,
                 * the last point at origin + horizon hours. */
                const originMs = Date.parse(data?.forecast_origin?.time_utc ?? '');
                const horizonH = Number(data?.forecast_horizon_h);
                const originT = Number.isFinite(originMs) ? originMs : null;
                const endT = originT != null && Number.isFinite(horizonH)
                    ? originT + horizonH * 3_600_000
                    : null;

                setState({
                    path,
                    ensemble,
                    ellipses,
                    hindcastPath: cleanPath(data?.observed?.reconstructed_path),
                    hindcastTrack: cleanTrack(data?.observed?.reconstructed_track),
                    staleGps: Boolean(data?.stale_gps),
                    originT,
                    endT,
                    generatedAt: typeof data?.generated_at === 'string' ? data.generated_at : null,
                });
            } catch {
                if (!cancelled) setState(EMPTY);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        load();
        const interval = setInterval(load, POLL_MS);
        return () => { cancelled = true; clearInterval(interval); };
    }, [deviceId]);

    return { ...state, loading };
}
