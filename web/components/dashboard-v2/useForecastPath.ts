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
    /** Wind-integrated "predicted hindcast" curve (last fix → now). Empty unless
     *  GPS is stale (and the forecast carries the field). Drawn instead of a
     *  straight last-fix→now connector. */
    predictedHindcast: ForecastPath;
    /** True when the last GPS fix is stale and the origin is dead-reckoned. */
    staleGps: boolean;
    /** True when the dead-reckon ran out of wind-cube coverage before reaching
     *  "now" — the origin is the last MODELED point (at originT), not the real
     *  present position, which is unknown. The UI should present "position
     *  uncertain since {originT}" rather than a confident current location. */
    coverageLimited: boolean;
    /** Set when the forecast was cut short at the predictability horizon (ensemble
     *  RMS spread crossed the threshold). The drawn path ends at `lonlat`; the map
     *  anchors a "forecast ends — paths diverge" notice there. Null otherwise. */
    divergence: { lonlat: [number, number]; spreadKm: number; thresholdKm: number } | null;
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
/* While the server reports a forecast is still computing (HTTP 202), poll fast
 * so it appears promptly — but cap the fast window so a device that can't be
 * forecast (e.g. no telemetry) doesn't hammer the endpoint. */
const FAST_POLL_MS = 8 * 1000;
const MAX_FAST_POLLS = 15; /* ~2 min, then settle to POLL_MS */

const EMPTY: Omit<UseForecastPathResult, 'loading'> = {
    path: [], ensemble: [], ellipses: [], hindcastPath: [], hindcastTrack: [],
    predictedHindcast: [], staleGps: false, coverageLimited: false, divergence: null,
    originT: null, endT: null, generatedAt: null,
};

/** Keep only well-formed [lon, lat] pairs. Latitude is range-checked (out-of-
 *  range lat crashes Mapbox); longitude is NOT bounded to ±180 — a long
 *  dead-reckon cone/path is built with CONTINUOUS longitudes that run past the
 *  antimeridian (e.g. 164°→190°), and clamping/dropping those shredded the
 *  50/90% zone at 180°. Mapbox renders out-of-[-180,180] longitudes fine. */
function cleanPath(raw: unknown): ForecastPath {
    if (!Array.isArray(raw)) return [];
    return raw.filter(
        (p: unknown): p is [number, number] =>
            Array.isArray(p) && p.length === 2 &&
            Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
            Math.abs(p[1]) <= 90,
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
            Math.abs(lat) <= 90 && Number.isFinite(t)
        ) {
            out.push({ lon, lat, t });
        }
    }
    return out;
}

/** Parse the forecast's `divergence` block (predictability-horizon termination),
 *  or null if absent/malformed. Longitude is kept as-is (may be unwrapped). */
function parseDivergence(raw: unknown): UseForecastPathResult['divergence'] {
    if (!raw || typeof raw !== 'object') return null;
    const d = raw as { lonlat?: unknown; spread_km?: unknown; threshold_km?: unknown };
    const ll = d.lonlat;
    if (!Array.isArray(ll) || ll.length !== 2) return null;
    const [lon, lat] = ll;
    if (typeof lon !== 'number' || typeof lat !== 'number' || !Number.isFinite(lon) || Math.abs(lat) > 90) return null;
    return {
        lonlat: [lon, lat],
        spreadKm: typeof d.spread_km === 'number' ? d.spread_km : 0,
        thresholdKm: typeof d.threshold_km === 'number' ? d.threshold_km : 0,
    };
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
        let timer: ReturnType<typeof setTimeout> | null = null;
        let fastPolls = 0;
        setLoading(true);

        async function load() {
            let nextDelay = POLL_MS;
            let pending = false;
            try {
                const res = await fetch(`/api/forecast?device=${encodeURIComponent(deviceId!)}`);
                if (res.status === 202) {
                    /* Server is computing in the background — poll fast for a
                     * short window, then settle to the slow cadence. The client
                     * never computes; it only reads. */
                    pending = true;
                    nextDelay = fastPolls++ < MAX_FAST_POLLS ? FAST_POLL_MS : POLL_MS;
                    return;
                }
                if (!res.ok) {
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
                    predictedHindcast: cleanPath(data?.predicted_hindcast?.path),
                    staleGps: Boolean(data?.stale_gps),
                    coverageLimited: Boolean(data?.stale_gps?.coverage_limited),
                    divergence: parseDivergence(data?.divergence),
                    originT,
                    endT,
                    generatedAt: typeof data?.generated_at === 'string' ? data.generated_at : null,
                });
                fastPolls = 0;
            } catch {
                if (!cancelled) setState(EMPTY);
            } finally {
                if (!cancelled) {
                    setLoading(pending);
                    timer = setTimeout(load, nextDelay);
                }
            }
        }

        load();
        return () => { cancelled = true; if (timer) clearTimeout(timer); };
    }, [deviceId]);

    return { ...state, loading };
}
