/**
 * Real Mapbox map for the dashboard-v2 screens. Replaces the stylized SVG
 * MapView in atoms.tsx, which was a design placeholder.
 *
 * Two modes:
 *  - Mission Control: many balloons (one per device's latest fix), plus the
 *    selected device's full track.
 *  - Device Tracker:  one balloon at the scrub time, plus the flight path
 *    truncated to the scrub time so the trail "draws in" as you scrub.
 *
 * Auto-fits the view to the data on first load and whenever the device set
 * or the active selection changes.
 *
 * Re-uses NEXT_PUBLIC_MAPBOX_TOKEN that already powers the v1 dashboard.
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef, LngLatBoundsLike } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import GatewayLayer from '@/components/maps/GatewayLayer';
import GatewayRangeRings from '@/components/maps/GatewayRangeRings';
import { quietBasemapLabels } from '@/components/maps/quietBasemapLabels';
import DayNightTerminator from '@/components/maps/DayNightTerminator';
import { applyBaseStyle } from '@/components/maps/baseStyle';
import { bathymetryAllZooms } from '@/components/maps/bathymetry';
import { ringKm } from '@/lib/gateways/range';
import { nearestFixTime, type PickablePathPoint } from '@/lib/telemetry/flightNarrative';
import { fmt } from './atoms';

export interface V2Balloon {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number | null;
}

export interface V2FlightPoint {
    lat: number;
    lon: number;
    t: number;
}

/** A gateway's location + reception strength for the most recent uplink.
 *  Many community TTN gateways don't publish their location; those are
 *  silently omitted (we only render pins for gateways with real lat/lon). */
export interface V2Gateway {
    gateway_id: string;
    lat: number;
    lon: number;
    rssi: number | null;
    snr: number | null;
}

/** Strict WGS84 — anything else crashes Mapbox (fitBounds, layers). */
export function isValidLngLat(lat: number, lon: number): boolean {
    return Number.isFinite(lat)
        && Number.isFinite(lon)
        && lat >= -90
        && lat <= 90
        && lon >= -180
        && lon <= 180;
}

/* Looser validity for forecast geometry that legitimately crosses the
 * antimeridian. A long dead-reckon cone is built with CONTINUOUS longitudes
 * that run past ±180 (e.g. 164°→190° around a 177°E center); `isValidLngLat`
 * would reject every vertex beyond 180 and shred the ring. Mapbox renders
 * out-of-[-180,180] longitudes fine (world copies), so only the latitude needs
 * guarding here — that's the value that actually crashes fitBounds/layers. */
function isRenderablePoint(lat: number, lon: number): boolean {
    return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90;
}

/* Unwrap a line/ring's longitudes so consecutive points never jump ~360°. A
 * geometry that straddles the antimeridian has vertices at e.g. +179 and −179;
 * Mapbox then draws the segment — or, for a polygon, the whole fill — the long
 * way around the globe, so the 50/90% cone (and any crossing path) breaks at
 * 180°. Letting longitude run past ±180 keeps the geometry continuous and
 * Mapbox renders it across the seam. No-op when nothing crosses 180°. */
function unwrapLngs(coords: Array<[number, number]>): Array<[number, number]> {
    if (coords.length < 2) return coords;
    const out: Array<[number, number]> = [coords[0]];
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

interface V2MissionMapProps {
    /** All balloons to render as markers. */
    balloons: V2Balloon[];
    /** Highlighted balloon id (rendered larger / accented). */
    activeId?: string | null;
    /** Trail for the active balloon, in chronological order. */
    flightPath?: V2FlightPoint[];
    /** When set, the auto-fit camera only considers flight-path points with
     *  `t <= playbackT` (so the view frames the flown-so-far track). Transmit
     *  dots are always drawn regardless. */
    playbackT?: number | null;
    /** When true, the map auto-fits to the active balloon + path on changes. */
    autoFit?: boolean;
    /** Optional projection — globe is nice for a world-scale view, mercator
     *  is better when zoomed in on a single mission. */
    projection?: 'globe' | 'mercator';
    /** TTN gateways that received the most recent uplink (with locations).
     *  Rendered as pins behind a user-controlled toggle so the map stays
     *  readable when the device isn't selected. */
    gateways?: V2Gateway[];
    /** When set, switches to the balloon-centered range view: the ambient
     *  coverage field is replaced by spreading-factor rings around this
     *  point, and the camera fits to the SF12 ring instead of the track. */
    rangeCenter?: { lat: number; lon: number; altM: number | null } | null;
    /** When true, render each transmitted GPS fix as a small dot in addition
     *  to the connecting flown-path line — distinguishing "where the balloon
     *  reported its position" from "where we think it flew between". */
    showTransmitPoints?: boolean;
    /** Predicted next track as [lon, lat] pairs (nominal forecast). Drawn as a
     *  dashed line ahead of the last fix. Empty / omitted = nothing drawn. */
    forecastPath?: Array<[number, number]>;
    /** Monte-Carlo ensemble members, each a [lon, lat] track — drawn as faint
     *  "spaghetti" behind the nominal line. */
    forecastEnsemble?: Array<Array<[number, number]>>;
    /** Per-slice 50/90% confidence ellipse polygons — drawn as the cone. */
    forecastEllipses?: Array<{ e50: Array<[number, number]>; e90: Array<[number, number]> }>;
    /** Wind-reconstructed likely prior path ([lon, lat]) — the hindcast. */
    hindcastPath?: Array<[number, number]>;
    /** The hindcast split into runs by certainty. Segments bridging a long gap
     *  since the last transmission are `estimated` and drawn tightly-dashed;
     *  the rest are drawn solid. When provided (and non-empty) it supersedes the
     *  plain `hindcastPath` line; `hindcastPath` remains the click-to-scrub
     *  target geometry. */
    hindcastSegments?: Array<{ coords: Array<[number, number]>; estimated: boolean }>;
    /** Two-point gray connector from the last fix to the assumed-now position
     *  while GPS is stale. Null / omitted = nothing drawn. */
    staleLine?: Array<[number, number]> | null;
    /** Basemap style — dark pairs with dashboard dark mode. */
    colorScheme?: 'light' | 'dark';
    /** Camera padding (px) — insets the focal region so fits/centers avoid
     *  overlapping chrome. On mobile a bottom inset lifts the globe clear of
     *  the floating timeline so it reads as centered. */
    viewPadding?: { top?: number; bottom?: number; left?: number; right?: number };
    /** GPS/hindcast path with timestamps — click map to scrub to nearest point. */
    pickPath?: PickablePathPoint[];
    onPickTime?: (t: number) => void;
    /** Instant (epoch ms) the day/night terminator should depict — the timeline
     *  scrub cursor, so day/night matches the time being viewed. Null = live (now). */
    terminatorDate?: number | null;
    /** True while the scrubber is being dragged — the terminator hides during the
     *  drag and fades back in at the settled time on release. */
    terminatorScrubbing?: boolean;
    /** Pixels to raise the map canvas above its window (clipped by the parent's
     *  overflow), lifting the globe clear of bottom chrome like the floating
     *  mobile timeline. The canvas grows taller by this amount so it still fills
     *  the window at all zooms; the globe simply centers higher. The visible
     *  lift is ~half this value. 0 = canvas fills its window exactly. */
    liftPx?: number;
    /** Zoom used for the wide "world-scale" default view — initial mount and the
     *  auto-fit onto the active balloon. Mobile passes a lower value to load a bit
     *  more zoomed out. Defaults to 2.5. */
    wideZoom?: number;
}

const PATH_PICK_MAX_KM = 120;

const MAP_STYLE_LIGHT = 'mapbox://styles/mapbox/light-v11';
const MAP_STYLE_DARK = 'mapbox://styles/mapbox/dark-v11';

function isWebGLAvailable(): boolean {
    if (typeof window === 'undefined') return false;
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
        return !!gl;
    } catch {
        return false;
    }
}

export default function V2MissionMap({
    balloons,
    activeId = null,
    flightPath = [],
    playbackT = null,
    autoFit = true,
    projection = 'globe',
    gateways = [],
    rangeCenter = null,
    showTransmitPoints = false,
    forecastPath = [],
    forecastEnsemble = [],
    forecastEllipses = [],
    hindcastPath = [],
    staleLine = null,
    colorScheme = 'light',
    viewPadding,
    hindcastSegments = [],
    pickPath = [],
    onPickTime,
    terminatorDate = null,
    terminatorScrubbing = false,
    liftPx = 0,
    wideZoom = 2.5,
}: V2MissionMapProps) {
    const mapStyle = colorScheme === 'dark' ? MAP_STYLE_DARK : MAP_STYLE_LIGHT;
    /* Track / forecast / receiver colors must shift with the basemap — the deep
     * navy forecast and brick-red track read fine on the light map but vanish on
     * the dark one, so dark mode swaps in brighter, higher-contrast hues. */
    const C = colorScheme === 'dark'
        ? { path: '#ff5b1f', forecast: '#5ba8ff', halo: 'rgba(255, 91, 31, 0.22)', recv: '74, 217, 155' }
        : { path: '#a11515', forecast: '#08327d', halo: 'rgba(161, 21, 21, 0.14)', recv: '122, 155, 118' };
    const pathPickEnabled = pickPath.length >= 2 && Boolean(onPickTime);
    const mapRef = useRef<MapRef>(null);
    const [styleLoaded, setStyleLoaded] = useState(false);
    const [webglOk, setWebglOk] = useState<boolean | null>(null);
    /* First load renders in visible stages — blank gray canvas, then the
     * terminator shade as a blob on the still-tileless map, then tiles, then
     * labels — which reads as a string of flashes. Hold an opaque cover over the
     * map until it has fully painted (Mapbox `idle` = tiles + all overlays
     * composited), then fade it away once for a single clean reveal. */
    const [revealed, setRevealed] = useState(false);

    /* GPU relief while the tab is hidden (#47). The globe holds a heavyweight
     * standing WebGL context (full-DPR canvas + the terminator's shader raster
     * layers + Black Marble tileset) that contends with e.g. a video call's
     * encode pipeline even when the map is idle. When the page is hidden for a
     * few seconds we tear the map down entirely (unmounting <Map> calls
     * map.remove(), freeing the context) and rebuild it on return, restoring the
     * exact camera. Gated on a delay so ordinary tab-flicking doesn't churn. */
    const [mapAlive, setMapAlive] = useState(true);
    const lastViewRef = useRef<{ longitude: number; latitude: number; zoom: number; bearing: number; pitch: number } | null>(null);

    /* The custom basemap (fog off, quieted labels, shaded relief, bathymetry) is
     * applied imperatively after the style loads. `styledata` fires many times on
     * first load — every Source/Layer react-map-gl mounts triggers it — and the
     * old code re-ran the whole restyle each time, so the map visibly repainted
     * over and over (the "flashes"). Run it only when it's actually needed: the
     * scheme changed, or a fresh style load wiped our layers (detected via a
     * sentinel). The repeated styledata bursts then become a cheap no-op. */
    const styledSchemeRef = useRef<'light' | 'dark' | null>(null);
    const applyCustomStyle = useCallback(() => {
        const m = mapRef.current?.getMap();
        if (!m) return;
        const SENTINEL = 'sl-bathymetry-v2';   /* added by bathymetryAllZooms */
        const layerGone = (() => { try { return !m.getLayer(SENTINEL); } catch { return true; } })();
        if (styledSchemeRef.current === colorScheme && !layerGone) return;
        try {
            m.setFog(null);
            quietBasemapLabels(m);
            applyBaseStyle(m, colorScheme);
            bathymetryAllZooms(m, colorScheme);
            styledSchemeRef.current = colorScheme;
        } catch { /* style mid-load; a later styledata retries */ }
    }, [colorScheme]);

    /* Telemetry can contain legacy / corrupt rows (e.g. lng stored in lat).
     * Never pass those to Mapbox — they hard-throw inside fitBounds. */
    const validBalloons = useMemo(
        () => balloons.filter(b => isValidLngLat(b.lat, b.lon)),
        [balloons],
    );
    const validFlightPath = useMemo(
        () => flightPath.filter(p => isValidLngLat(p.lat, p.lon)),
        [flightPath],
    );
    /* Gateways without published location are omitted from the map but still
     * appear in the GatewaysPanel's list. */
    const validGateways = useMemo(
        () => gateways.filter(g => isValidLngLat(g.lat, g.lon)),
        [gateways],
    );

    useEffect(() => {
        setWebglOk(isWebGLAvailable());
    }, []);

    /* Safety net: reveal anyway if `idle` is slow to fire (e.g. tiles still
     * trickling on a poor connection) so the map can never stay hidden. */
    useEffect(() => {
        if (!styleLoaded || revealed) return;
        const id = setTimeout(() => setRevealed(true), 3000);
        return () => clearTimeout(id);
    }, [styleLoaded, revealed]);

    /* Style flag must reset when the projection forces a remount. */
    useEffect(() => { setStyleLoaded(false); }, [projection]);

    /* Camera padding (focal-region inset). Folded into every fit/fly below so
     * the bottom inset isn't clobbered when fitBounds rewrites map padding. */
    const padTop = viewPadding?.top ?? 0;
    const padBottom = viewPadding?.bottom ?? 0;
    const padLeft = viewPadding?.left ?? 0;
    const padRight = viewPadding?.right ?? 0;
    const pad = (extra: number) => ({
        top: padTop + extra,
        bottom: padBottom + extra,
        left: padLeft + extra,
        right: padRight + extra,
    });

    /* Apply padding directly for the no-fit case (e.g. no data yet) so the
     * focal region sits where the fits put it rather than behind the chrome.
     * (Mobile lifts the globe via a CSS canvas offset, not camera padding —
     * see `liftPx` — so this stays at the requested insets, usually zero.) */
    useEffect(() => {
        const map = mapRef.current;
        if (!map || !styleLoaded) return;
        try { map.setPadding({ top: padTop, bottom: padBottom, left: padLeft, right: padRight }); } catch { /* ignore */ }
    }, [styleLoaded, padTop, padBottom, padLeft, padRight]);

    /* Initial view — center on the balloon at the wide default zoom, else US. */
    const initialView = useMemo(() => {
        const focus = validBalloons.find(b => b.id === activeId) ?? validBalloons[0];
        if (focus) {
            return { longitude: focus.lon, latitude: focus.lat, zoom: wideZoom };
        }
        return { longitude: -98, latitude: 39, zoom: wideZoom };
        /* eslint-disable-next-line react-hooks/exhaustive-deps */
    }, []); /* only used at mount */

    /* Tear the map down when the page has been hidden for a moment; rebuild on
     * return. See `mapAlive` above. */
    useEffect(() => {
        const HIDE_TEARDOWN_MS = 8000;   /* don't churn on quick tab flicks */
        let timer: ReturnType<typeof setTimeout> | null = null;
        const onVisibility = () => {
            if (document.hidden) {
                if (timer) return;
                timer = setTimeout(() => {
                    timer = null;
                    /* Snapshot the camera so the rebuild lands on the same view. */
                    const m = mapRef.current?.getMap();
                    if (m) {
                        try {
                            const c = m.getCenter();
                            lastViewRef.current = {
                                longitude: c.lng, latitude: c.lat,
                                zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch(),
                            };
                        } catch { /* map mid-teardown; keep the previous snapshot */ }
                    }
                    setRevealed(false);
                    setStyleLoaded(false);
                    setMapAlive(false);
                }, HIDE_TEARDOWN_MS);
            } else {
                if (timer) { clearTimeout(timer); timer = null; }
                setMapAlive(true);   /* remounts <Map> at lastViewRef if torn down */
            }
        };
        document.addEventListener('visibilitychange', onVisibility);
        return () => {
            if (timer) clearTimeout(timer);
            document.removeEventListener('visibilitychange', onVisibility);
        };
    }, []);

    /* Auto-fit policy: fit once per activeId selection, then leave the camera
     * alone so live data updates and scrubbing don't yank the view back. The
     * user can pan / zoom freely; switching devices re-fits. */
    const fittedActiveRef = useRef<string | null | undefined>(undefined);
    useEffect(() => {
        if (!autoFit) return;
        /* Range mode owns the camera — skip the track fit so the two don't
         * fight. Reset the ref so exiting range mode re-fits to the track. */
        if (rangeCenter) {
            fittedActiveRef.current = undefined;
            return;
        }
        const map = mapRef.current;
        if (!map || !styleLoaded) return;
        if (fittedActiveRef.current === (activeId ?? null)) return;

        /* The very first fit (e.g. after balloon data arrives post-mount) should
         * snap instantly — animating would show the fallback view and then rotate/
         * zoom over to the balloon. Later device switches animate. */
        const firstFit = fittedActiveRef.current === undefined;
        const fitDuration = firstFit ? 0 : 1200;

        /* Keep camera updates out of uncaught rejects from mapbox-gl. */
        try {
            const active = validBalloons.find(b => b.id === activeId);
            if (active) {
                /* On load, center on the selected balloon at the wide zoom rather
                 * than zooming in to fit the whole track — the user zooms in from
                 * there. */
                map.flyTo({ center: [active.lon, active.lat], zoom: wideZoom, duration: fitDuration, padding: pad(0) });
                fittedActiveRef.current = activeId ?? null;
                return;
            }

            /* No active selection — frame the whole fleet. */
            const lats: number[] = [];
            const lons: number[] = [];
            validBalloons.forEach(b => { lats.push(b.lat); lons.push(b.lon); });
            if (lats.length === 0) return;

            const minLat = Math.min(...lats);
            const maxLat = Math.max(...lats);
            const minLon = Math.min(...lons);
            const maxLon = Math.max(...lons);
            if (minLat < -90 || maxLat > 90 || minLon < -180 || maxLon > 180) return;

            if (lats.length === 1) {
                map.flyTo({ center: [lons[0], lats[0]], zoom: wideZoom, duration: fitDuration, padding: pad(0) });
            } else {
                map.fitBounds([[minLon, minLat], [maxLon, maxLat]] as LngLatBoundsLike, {
                    padding: pad(60),
                    duration: fitDuration,
                    maxZoom: 5,
                });
            }
            fittedActiveRef.current = activeId ?? null;
        } catch (e) {
            console.warn('V2MissionMap camera update skipped', e);
        }
    }, [autoFit, styleLoaded, activeId, validBalloons, validFlightPath, playbackT, rangeCenter]);

    /* Range-mode camera: fit to the SF12 ring around the balloon. Keyed on
     * activeId so it fits once on entering range mode (and on device change),
     * not on every scrub tick — the user can then pan / zoom freely. */
    const rangeFittedRef = useRef<string | null>(null);
    useEffect(() => {
        if (!rangeCenter) {
            rangeFittedRef.current = null;
            return;
        }
        const map = mapRef.current;
        if (!map || !styleLoaded) return;
        const key = activeId ?? 'range';
        if (rangeFittedRef.current === key) return;
        try {
            const maxKm = ringKm('sf12', rangeCenter.altM);
            const r = Number.isFinite(maxKm) ? maxKm : 600;
            const latPad = r / 111;
            const lonPad = r / (111 * Math.max(0.2, Math.cos((rangeCenter.lat * Math.PI) / 180)));
            const minLon = rangeCenter.lon - lonPad;
            const maxLon = rangeCenter.lon + lonPad;
            const minLat = rangeCenter.lat - latPad;
            const maxLat = rangeCenter.lat + latPad;
            if (minLat < -90 || maxLat > 90 || minLon < -180 || maxLon > 180) return;
            map.fitBounds([[minLon, minLat], [maxLon, maxLat]] as LngLatBoundsLike, {
                padding: pad(50),
                duration: 800,
                maxZoom: 11,
            });
            rangeFittedRef.current = key;
        } catch (e) {
            console.warn('V2MissionMap range fit skipped', e);
        }
    }, [rangeCenter, styleLoaded, activeId]);

    const balloonGeoJSON = useMemo(() => ({
        type: 'FeatureCollection' as const,
        features: validBalloons.map(b => ({
            type: 'Feature' as const,
            id: b.id,
            geometry: { type: 'Point' as const, coordinates: [b.lon, b.lat] },
            properties: {
                deviceId: b.id,
                altitude: b.altitude_m ?? 0,
                isActive: b.id === activeId ? 1 : 0,
            },
        })),
    }), [validBalloons, activeId]);

    /* Transmitted-position dots — one per GPS fix (respecting playback time).
     * These are the raw points the balloon actually reported. No line connects
     * them: the route flown between sparse fixes is unknown, so the hindcast is
     * the honest estimate of the path between them. */
    const transmitPointsGeoJSON = useMemo(() => {
        /* Every transmitted fix is always shown — the dots mark where the
         * balloon actually reported in, independent of the scrub position. */
        if (validFlightPath.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: validFlightPath.map(p => ({
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] as [number, number] },
                properties: {},
            })),
        };
    }, [validFlightPath]);

    /* Forecast line — predicted nominal track ahead of the last fix. Filtered
     * to valid WGS84 so a bad endpoint can't crash Mapbox. */
    const forecastGeoJSON = useMemo(() => {
        const pts = forecastPath.filter(([lon, lat]) => isRenderablePoint(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                geometry: { type: 'LineString' as const, coordinates: unwrapLngs(pts) },
                properties: {},
            }],
        };
    }, [forecastPath]);

    /* Hindcast — the wind-reconstructed likely path through GPS gaps. Used for
     * the click-to-scrub target line; the visible line is drawn from the
     * certainty-split segments below when those are available. */
    const hindcastGeoJSON = useMemo(() => {
        const pts = hindcastPath.filter(([lon, lat]) => isRenderablePoint(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: unwrapLngs(pts) }, properties: {} }],
        };
    }, [hindcastPath]);

    /* Certainty-split hindcast: solid for confident segments, tightly-dashed
     * "estimated" for those bridging a long transmission gap. */
    const hasHindcastSegments = hindcastSegments.length > 0;
    const hindcastRuns = (estimated: boolean) => {
        const runs = hindcastSegments
            .filter(s => s.estimated === estimated && s.coords.length >= 2)
            .map(s => unwrapLngs(s.coords));
        if (!runs.length) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{ type: 'Feature' as const, geometry: { type: 'MultiLineString' as const, coordinates: runs }, properties: {} }],
        };
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const hindcastCertainGeoJSON = useMemo(() => hindcastRuns(false), [hindcastSegments]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const hindcastEstimatedGeoJSON = useMemo(() => hindcastRuns(true), [hindcastSegments]);

    /* Stale-GPS connector — last real fix → dead-reckoned "assumed now". */
    const staleLineGeoJSON = useMemo(() => {
        const pts = (staleLine ?? []).filter(([lon, lat]) => isRenderablePoint(lat, lon));
        if (pts.length < 2) return null;
        return {
            type: 'FeatureCollection' as const,
            features: [{ type: 'Feature' as const, geometry: { type: 'LineString' as const, coordinates: unwrapLngs(pts) }, properties: {} }],
        };
    }, [staleLine]);

    /* Light-touch on-map label: a single quiet tag at the most recent real GPS
     * fix ("last fix · 3h ago"), so the viewer can place the freshest report
     * without a separate legend. Small, uppercase, with a basemap-matched halo
     * so it stays legible (incl. over the dark night side) while reading as an
     * annotation, not chrome. Path-type tags ("reconstructed"/"forecast") were
     * tried here but read too loud, so the line styling carries that distinction
     * instead. Only the active balloon carries a flight path. */
    const labelGeoJSON = useMemo(() => {
        const lastFix = validFlightPath.length ? validFlightPath[validFlightPath.length - 1] : null;
        if (!lastFix) return null;
        const halo = colorScheme === 'dark' ? 'rgba(8, 12, 16, 0.85)' : 'rgba(255, 255, 255, 0.9)';
        const color = colorScheme === 'dark' ? '#e6ebf2' : '#33373d';
        const age = Date.now() - lastFix.t;
        const label = Number.isFinite(age) && age >= 0 ? `last fix · ${fmt.duration(age)} ago` : 'last fix';
        return {
            type: 'FeatureCollection' as const,
            features: [{
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: [lastFix.lon, lastFix.lat] as [number, number] },
                properties: { label, color, halo },
            }],
        };
    }, [validFlightPath, colorScheme]);

    /* Ensemble "spaghetti" — every Monte-Carlo member as a faint line. */
    const ensembleGeoJSON = useMemo(() => {
        const tracks = forecastEnsemble
            .map(t => t.filter(([lon, lat]) => isRenderablePoint(lat, lon)))
            .filter(t => t.length >= 2)
            .map(unwrapLngs);
        if (tracks.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: tracks.map(t => ({
                type: 'Feature' as const,
                geometry: { type: 'LineString' as const, coordinates: t },
                properties: {},
            })),
        };
    }, [forecastEnsemble]);

    /* Confidence cones — 50% and 90% ellipse polygons per forecast slice.
     * A polygon needs ≥3 points and a closed ring; Mapbox closes it for us. */
    const ellipsePolys = useMemo(() => {
        const e50: Array<[number, number][]> = [];
        const e90: Array<[number, number][]> = [];
        for (const slice of forecastEllipses) {
            const p50 = slice.e50.filter(([lon, lat]) => isRenderablePoint(lat, lon));
            const p90 = slice.e90.filter(([lon, lat]) => isRenderablePoint(lat, lon));
            if (p50.length >= 3) e50.push(unwrapLngs(p50));
            if (p90.length >= 3) e90.push(unwrapLngs(p90));
        }
        const toFC = (rings: Array<[number, number][]>) => rings.length === 0 ? null : ({
            type: 'FeatureCollection' as const,
            features: rings.map(ring => ({
                type: 'Feature' as const,
                geometry: { type: 'Polygon' as const, coordinates: [ring] },
                properties: {},
            })),
        });
        return { e50: toFC(e50), e90: toFC(e90) };
    }, [forecastEllipses]);

    /* Gateway pins — coloured by signal strength so the strongest gateways
     * (closest, best-LOS) read as accent green and the weakest (long-range,
     * just-barely-receiving) as muted amber. Reception lines are deliberately
     * thin so the balloon's flight path stays the visual primary. */
    const gatewaysGeoJSON = useMemo(() => ({
        type: 'FeatureCollection' as const,
        features: validGateways.map(g => ({
            type: 'Feature' as const,
            id: g.gateway_id,
            geometry: { type: 'Point' as const, coordinates: [g.lon, g.lat] },
            properties: {
                gateway_id: g.gateway_id,
                rssi: g.rssi ?? -130,    /* worst-case fallback for the colour ramp */
                snr: g.snr ?? -10,
            },
        })),
    }), [validGateways]);

    /* Reception lines from the active balloon to each gateway that heard it
     * — provides immediate visual confirmation of "who is listening to me
     * right now". Only drawn when an active balloon has a position. */
    const receptionLinesGeoJSON = useMemo(() => {
        const active = validBalloons.find(b => b.id === activeId);
        if (!active || validGateways.length === 0) return null;
        return {
            type: 'FeatureCollection' as const,
            features: validGateways.map(g => ({
                type: 'Feature' as const,
                geometry: {
                    type: 'LineString' as const,
                    coordinates: [
                        [active.lon, active.lat],
                        [g.lon, g.lat],
                    ] as [number, number][],
                },
                properties: { rssi: g.rssi ?? -130 },
            })),
        };
    }, [validBalloons, activeId, validGateways]);

    /* Keep the active balloon marker on top of everything. react-map-gl appends
     * each <Layer> in mount order, and layers whose data arrives after the
     * balloon — gateway pins, reception lines, the forecast cone / ensemble /
     * hindcast — would otherwise paint over the balloon dot.
     *
     * A React effect alone races: react-map-gl reconciles new layers into the
     * style asynchronously, so on the first scrub the gateway layer lands AFTER
     * the effect has already raised the balloon (it only sorted out on the next
     * click). Instead, re-raise on the map's own `styledata` event, which fires
     * whenever the layer set changes — including react-map-gl's async adds. A
     * guard skips when the balloon is already topmost so our own moveLayer (which
     * itself fires styledata) doesn't loop. */
    useEffect(() => {
        const m = mapRef.current?.getMap();
        if (!m || !styleLoaded) return;
        const raise = () => {
            try {
                const layers = m.getStyle()?.layers;
                if (!layers || !m.getLayer('v2-balloon-core')) return;
                if (layers[layers.length - 1]?.id === 'v2-balloon-core') return;  /* already on top */
                for (const id of ['v2-balloon-halo', 'v2-balloon-core']) {
                    if (m.getLayer(id)) m.moveLayer(id);   /* no beforeId → move to top */
                }
            } catch { /* style mid-update; the next styledata retries */ }
        };
        raise();
        m.on('styledata', raise);
        return () => { m.off('styledata', raise); };
    }, [styleLoaded]);

    if (webglOk === false) {
        return (
            <div style={{
                width: '100%', height: '100%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--sl-bg-1)', color: 'var(--sl-text-dim2)',
                fontSize: 11, padding: 24, textAlign: 'center',
            }}>
                <div>
                    <div style={{ color: 'var(--sl-alert)', marginBottom: 6, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
                        Map unavailable
                    </div>
                    <div style={{ maxWidth: 360, lineHeight: 1.5 }}>
                        Browser can&apos;t create a WebGL context. Enable hardware acceleration
                        (chrome://settings/system) and reload.
                    </div>
                </div>
            </div>
        );
    }

    if (webglOk === null) {
        /* Tiny placeholder before the feature check completes. */
        return <div style={{ width: '100%', height: '100%', background: 'var(--sl-bg-1)' }} />;
    }

    /* If there's no token configured, the user gets a clear hint instead
     * of a silent blank canvas. */
    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
        return (
            <div style={{
                width: '100%', height: '100%', background: 'var(--sl-bg-1)',
                color: 'var(--sl-text-dim2)', fontSize: 11, padding: 16,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                NEXT_PUBLIC_MAPBOX_TOKEN not configured.
            </div>
        );
    }

    return (
        <div
            style={{
                position: 'absolute',
                /* Extend the canvas `liftPx` above its window and keep the bottom
                 * pinned, so it stays full-width/height-plus and the globe (canvas-
                 * centered) sits higher. The parent clips the overflow. */
                top: -liftPx,
                bottom: 0,
                left: 0,
                right: 0,
                cursor: pathPickEnabled ? 'crosshair' : undefined,
            }}
        >
            {mapAlive ? (
            <Map
                ref={mapRef}
                /* Keyed on projection only — a projection switch needs a clean
                 * remount, but a theme switch must NOT (it would reset the
                 * camera). The basemap swaps in place via the `mapStyle` prop,
                 * which preserves center/zoom; custom layers re-apply on
                 * styledata. */
                key={projection}
                mapboxAccessToken={token}
                /* Restore the pre-teardown camera on a hidden-tab rebuild (#47);
                 * `initialViewState` is only read at mount. */
                initialViewState={lastViewRef.current ?? initialView}
                style={{ width: '100%', height: '100%' }}
                mapStyle={mapStyle}
                projection={projection === 'globe' ? 'globe' : 'mercator'}
                onClick={(e) => {
                    if (!pathPickEnabled || !onPickTime) return;
                    /* Snap to the nearest transmitted fix (the dots), not an
                     * interpolated point along the path — and do nothing when the
                     * click lands far from any transmission. */
                    const t = nearestFixTime(validFlightPath, e.lngLat.lng, e.lngLat.lat, PATH_PICK_MAX_KM);
                    if (t == null) return;
                    onPickTime(t);
                }}
                onLoad={() => {
                    setStyleLoaded(true);
                    applyCustomStyle();
                    /* Reveal once the map has settled (tiles loaded + everything
                     * composited), so the staged paint happens behind the cover. */
                    const m = mapRef.current?.getMap();
                    if (m) m.once('idle', () => setRevealed(true));
                }}
                onStyleData={() => {
                    setStyleLoaded(true);
                    applyCustomStyle();
                }}
                attributionControl={false}
                logoPosition="bottom-left"
            >
                {styleLoaded && (
                    <>
                        {/* Day/night terminator — deferred until after the map is
                          * revealed. It carries the heaviest sources (the per-pixel
                          * twilight shader + the third-party Black Marble night-
                          * lights tileset), so keeping it off the initial critical
                          * path lets the basemap reach `idle` (and reveal) fast.
                          * Once mounted it fades itself in (see its first-reveal
                          * fade). Rendered first so it dims only the basemap;
                          * coverage, paths and pins sit on top. */}
                        {revealed && (
                            <DayNightTerminator colorScheme={colorScheme} date={terminatorDate} scrubbing={terminatorScrubbing} />
                        )}

                        {/* Static TTN ground-station coverage — sits at
                          * the bottom of the layer stack so flight paths
                          * and balloon pins render on top. In range mode the
                          * ambient field is replaced by balloon-centered SF
                          * rings + nearby gateways. */}
                        {rangeCenter ? (
                            <GatewayRangeRings
                                lat={rangeCenter.lat}
                                lon={rangeCenter.lon}
                                altM={rangeCenter.altM}
                            />
                        ) : (
                            <GatewayLayer colorScheme={colorScheme} />
                        )}
                        {/* No straight line is drawn between transmitted fixes:
                          * we don't actually know the route flown between sparse
                          * reports, so connecting them would imply precision we
                          * don't have. The transmitted dots show where the balloon
                          * actually reported; the hindcast below is the honest
                          * wind-reconstructed estimate of the path between them. */}

                        {/* Hindcast — wind-reconstructed likely prior path
                          * (deep blue, dashed): the best estimate of the route
                          * between transmitted fixes. */}
                        {hindcastGeoJSON && (
                            <Source id="v2-hindcast" type="geojson" data={hindcastGeoJSON}>
                                {/* Plain solid line — only when we don't have the
                                  * certainty-split segments (else the split lines
                                  * below render the visible path). */}
                                {!hasHindcastSegments && (
                                    <Layer
                                        id="v2-hindcast-line"
                                        type="line"
                                        layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                        paint={{
                                            'line-color': C.path,
                                            'line-width': 2,
                                            'line-opacity': 0.85,
                                        }}
                                    />
                                )}
                                {pathPickEnabled && (
                                    <Layer
                                        id="v2-hindcast-pick"
                                        type="line"
                                        layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                        paint={{
                                            'line-color': C.path,
                                            'line-width': 14,
                                            'line-opacity': 0.01,
                                        }}
                                    />
                                )}
                            </Source>
                        )}

                        {/* Confident hindcast segments — solid. */}
                        {hindcastCertainGeoJSON && (
                            <Source id="v2-hindcast-certain" type="geojson" data={hindcastCertainGeoJSON}>
                                <Layer
                                    id="v2-hindcast-certain-line"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{
                                        'line-color': C.path,
                                        'line-width': 2,
                                        'line-opacity': 0.85,
                                    }}
                                />
                            </Source>
                        )}

                        {/* Estimated hindcast segments (long gap since last
                          * transmission) — tightly-dashed + slightly dimmer to
                          * read as less certain. */}
                        {hindcastEstimatedGeoJSON && (
                            <Source id="v2-hindcast-estimated" type="geojson" data={hindcastEstimatedGeoJSON}>
                                <Layer
                                    id="v2-hindcast-estimated-line"
                                    type="line"
                                    layout={{ 'line-cap': 'butt', 'line-join': 'round' }}
                                    paint={{
                                        'line-color': C.path,
                                        'line-width': 2,
                                        'line-opacity': 0.7,
                                        'line-dasharray': [1.5, 1.5],
                                    }}
                                />
                            </Source>
                        )}

                        {/* Stale-GPS connector — last real fix → dead-reckoned
                          * "assumed now", drawn gray so it reads as inferred. */}
                        {staleLineGeoJSON && (
                            <Source id="v2-stale-line" type="geojson" data={staleLineGeoJSON}>
                                <Layer
                                    id="v2-stale-line-stroke"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{
                                        'line-color': 'rgba(90, 110, 135, 0.85)',
                                        'line-width': 2,
                                        'line-dasharray': [3, 3],
                                        'line-opacity': 0.8,
                                    }}
                                />
                            </Source>
                        )}

                        {/* Confidence cone — 90% ellipses (dashed outline) then
                          * 50% ellipses (filled), so the spread reads from wide
                          * to tight. Drawn first so everything else sits on top. */}
                        {ellipsePolys.e90 && (
                            <Source id="v2-forecast-e90" type="geojson" data={ellipsePolys.e90}>
                                <Layer
                                    id="v2-forecast-e90-stroke"
                                    type="line"
                                    paint={{
                                        'line-color': C.forecast,
                                        'line-width': 1,
                                        'line-opacity': 0.4,
                                        'line-dasharray': [3, 4],
                                    }}
                                />
                            </Source>
                        )}
                        {ellipsePolys.e50 && (
                            <Source id="v2-forecast-e50" type="geojson" data={ellipsePolys.e50}>
                                <Layer
                                    id="v2-forecast-e50-fill"
                                    type="fill"
                                    paint={{ 'fill-color': C.forecast, 'fill-opacity': 0.1 }}
                                />
                                <Layer
                                    id="v2-forecast-e50-stroke"
                                    type="line"
                                    paint={{ 'line-color': C.forecast, 'line-width': 1, 'line-opacity': 0.5 }}
                                />
                            </Source>
                        )}

                        {/* Ensemble spaghetti — faint individual Monte-Carlo runs. */}
                        {ensembleGeoJSON && (
                            <Source id="v2-forecast-ensemble" type="geojson" data={ensembleGeoJSON}>
                                <Layer
                                    id="v2-forecast-ensemble-lines"
                                    type="line"
                                    layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                                    paint={{ 'line-color': C.forecast, 'line-width': 1, 'line-opacity': 0.1 }}
                                />
                            </Source>
                        )}

                        {/* Forecast — predicted nominal track, dashed + amber so
                          * it reads clearly as "future / uncertain" against the
                          * solid teal flown path. Sits under the transmit dots
                          * and balloon pins. */}
                        {forecastGeoJSON && (
                            <Source id="v2-forecast-path" type="geojson" data={forecastGeoJSON}>
                                <Layer
                                    id="v2-forecast-line"
                                    type="line"
                                    paint={{
                                        'line-color': C.forecast,
                                        'line-opacity': 0.8,
                                        'line-dasharray': [2, 2],
                                        'line-width': [
                                            'interpolate', ['linear'], ['zoom'],
                                            3, 1.2,
                                            8, 1.8,
                                            14, 2.6,
                                        ],
                                    }}
                                />
                            </Source>
                        )}

                        {/* Transmitted-position dots — the raw points the balloon
                          * reported. Drawn on top of the flown-path line so each
                          * uplink reads as a distinct fix. */}
                        {showTransmitPoints && transmitPointsGeoJSON && (
                            <Source id="v2-transmit-points" type="geojson" data={transmitPointsGeoJSON}>
                                <Layer
                                    id="v2-transmit-point"
                                    type="circle"
                                    paint={{
                                        /* Hollow ringed nodes — a white core with a
                                          * blueprint-azure ring reads as a surveyed
                                          * "reported here" point against the solid
                                          * azure flown-path line. */
                                        'circle-color': '#ffffff',
                                        'circle-radius': [
                                            'interpolate', ['linear'], ['zoom'],
                                            3, 1.5,
                                            8, 2.1,
                                            14, 3.0,
                                        ],
                                        'circle-opacity': 1,
                                        'circle-stroke-width': 1.1,
                                        'circle-stroke-color': C.path,
                                    }}
                                />
                            </Source>
                        )}

                        {/* Reception lines render BEHIND the balloon/gateway pins so
                          * the pins always sit on top. */}
                        {receptionLinesGeoJSON && (
                            <Source id="v2-reception-lines" type="geojson" data={receptionLinesGeoJSON}>
                                <Layer
                                    id="v2-reception-line"
                                    type="line"
                                    paint={{
                                        /* Reception threads stay quiet neutral so the
                                          * red track is the only saturated line. */
                                        'line-color': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, `rgba(${C.recv}, 0.18)`,
                                            -100, `rgba(${C.recv}, 0.40)`,
                                             -85, `rgba(${C.recv}, 0.62)`,
                                        ],
                                        'line-width': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, 0.6,
                                             -85, 1.4,
                                        ],
                                    }}
                                />
                            </Source>
                        )}

                        {validGateways.length > 0 && (
                            <Source id="v2-gateways" type="geojson" data={gatewaysGeoJSON}>
                                <Layer
                                    id="v2-gateway-pin"
                                    type="circle"
                                    paint={{
                                        /* Gateways as quiet slate survey dots — strength
                                          * shown by going from pale to deep slate. */
                                        'circle-color': [
                                            'interpolate', ['linear'], ['get', 'rssi'],
                                            -130, '#b9cbb6',   /* marginal */
                                            -100, '#9bb398',
                                             -80, '#7a9b76',   /* strong */
                                        ],
                                        'circle-radius': 4.5,
                                        'circle-stroke-width': 1,
                                        'circle-stroke-color': 'rgba(255, 255, 255, 0.95)',
                                        'circle-stroke-opacity': 0.95,
                                    }}
                                />
                            </Source>
                        )}

                        <Source id="v2-balloons" type="geojson" data={balloonGeoJSON}>
                            <Layer
                                id="v2-balloon-halo"
                                type="circle"
                                filter={['==', ['get', 'isActive'], 1]}
                                paint={{
                                    'circle-color': C.halo,
                                    'circle-radius': 11,
                                    'circle-blur': 0.5,
                                }}
                            />
                            <Layer
                                id="v2-balloon-core"
                                type="circle"
                                paint={{
                                    'circle-color': [
                                        'case', ['==', ['get', 'isActive'], 1],
                                        C.path,
                                        '#8a8f88',
                                    ],
                                    'circle-radius': [
                                        'case', ['==', ['get', 'isActive'], 1],
                                        5,
                                        3.5,
                                    ],
                                    /* Crisp white keyline so the dot reads as a precise
                                     * survey marker, not a soft glow. */
                                    'circle-stroke-width': 1.5,
                                    'circle-stroke-color': '#ffffff',
                                    'circle-stroke-opacity': 1,
                                }}
                            />
                        </Source>

                        {/* Light-touch orienting label — a small uppercase tag at the
                          * last real fix ("last fix · 3h ago"). The basemap-matched
                          * halo keeps it legible without a box. */}
                        {labelGeoJSON && (
                            <Source id="v2-map-labels" type="geojson" data={labelGeoJSON}>
                                <Layer
                                    id="v2-map-label"
                                    type="symbol"
                                    layout={{
                                        'text-field': ['get', 'label'],
                                        'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
                                        'text-size': 11,
                                        'text-transform': 'uppercase',
                                        'text-letter-spacing': 0.08,
                                        'text-offset': [0, -0.9],
                                        'text-anchor': 'bottom',
                                        'text-padding': 6,
                                        'text-allow-overlap': false,
                                        'text-optional': true,
                                    }}
                                    paint={{
                                        'text-color': ['get', 'color'],
                                        'text-opacity': 0.9,
                                        'text-halo-color': ['get', 'halo'],
                                        'text-halo-width': 1.4,
                                        'text-halo-blur': 0.4,
                                    }}
                                />
                            </Source>
                        )}
                    </>
                )}
            </Map>
            ) : (
                /* Torn down while hidden (#47) — a plain panel holds the layout
                 * (and frees the WebGL context) until the tab is visible again. */
                <div aria-hidden style={{ position: 'absolute', inset: 0, background: 'var(--sl-bg-1)' }} />
            )}

            {/* Load cover — opaque until the map has fully painted, then fades
              * away once so the staged first-load render (gray canvas → shade
              * blob → tiles → labels) is never seen. Matches the surrounding
              * surface so it's seamless with the chrome around the map. */}
            <div
                aria-hidden
                style={{
                    position: 'absolute', inset: 0, zIndex: 3,
                    background: 'var(--sl-bg-1)',
                    opacity: revealed ? 0 : 1,
                    transition: 'opacity 450ms ease',
                    pointerEvents: 'none',
                }}
            />

            {/* Editorial attribution — Mapbox's control styling is finicky and
              * clips at the viewport edge, so we render our own (the Mapbox
              * wordmark stays via logoPosition, satisfying terms alongside
              * these source credits). */}
            <div style={{
                position: 'absolute', bottom: 12, right: 13, zIndex: 1,
                fontFamily: 'var(--sl-mono)', fontSize: 8, letterSpacing: '0.03em',
                color: 'var(--sl-text-dim3)', opacity: 0.7, pointerEvents: 'auto',
            }}>
                <a href="https://www.mapbox.com/about/maps/" target="_blank" rel="noreferrer noopener"
                   style={{ color: 'inherit', textDecoration: 'none' }}>Mapbox</a>
                <span style={{ opacity: 0.5 }}> · </span>
                <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer noopener"
                   style={{ color: 'inherit', textDecoration: 'none' }}>OpenStreetMap</a>
            </div>
        </div>
    );
}
