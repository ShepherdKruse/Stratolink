/**
 * Stratolink dashboard v2 — shared atoms.
 *
 * Direct port of the design's components.jsx into typed React. Every atom is
 * deliberately presentational: it takes data and renders pixels, no fetching
 * and no placeholder values. Data comes from useTelemetry() in the screen.
 */
'use client';

import type { ReactNode } from 'react';

/* ──────────────────────────────────────────────────────────────
 * Telemetry shape used across v2 — mirrors the design system's data
 * vocabulary so the atoms drop in 1:1.
 * ────────────────────────────────────────────────────────────── */
export interface TelemetryRow {
    /** Epoch ms timestamp of the uplink. */
    t: number;
    lat: number | null;
    lon: number | null;
    /** GPS-reported altitude (m). Null when the firmware had no fix. */
    alt: number | null;
    temp: number | null;
    /** Barometric pressure in hPa (parser already divides firmware's 0.1-hPa
     *  uint16 by 10 on insert). */
    pres: number | null;
    /** Pressure-derived altitude (m above MSL) using USSA-1976 ISA. Computed
     *  in `useTelemetry.rawToTelemetry` so every consumer sees the same value
     *  without re-deriving. Null whenever `pres` is null or out of range. */
    presAlt: number | null;
    batt: number | null;
    sol: number | null;
    rssi: number | null;
    snr: number | null;
    sats: number | null;
    lux: number | null;
    uv: number | null;
    spd: number | null;
    hdg: number | null;
    ax: number | null;
    ay: number | null;
    az: number | null;
    vx: number | null;
    vy: number | null;
    /* Firmware-side system state (may be null until firmware emits them). */
    firmware_version: string | null;
    uptime_s: number | null;
    tx_count: number | null;
    hdop: number | null;
    power_mode: string | null;
    sleep_ms: number | null;
    lora_sf: number | null;
    lora_bw: number | null;
    frequency_hz: number | null;
    /* Per-uplink gateway list from TTN's rx_metadata. Empty array (not null)
     * when the parser succeeded but rx_metadata was absent — easier to query
     * than a NULL-vs-[] split. */
    gateways: GatewayReception[] | null;
}

/** One gateway's reception of a single uplink — mirrors the parser's shape. */
export interface GatewayReception {
    gateway_id: string;
    rssi: number | null;
    snr: number | null;
    lat: number | null;
    lon: number | null;
    alt: number | null;
}

export interface DeviceInfo {
    id: string;
    firmware: string | null;
    launched_by: string | null;
    launched_at: number | null;
    freq_mhz: number | null;
    sf: string | null;
    packet_count: number;
}

/* ──────────────────────────────────────────────────────────────
 * Formatting helpers
 * ────────────────────────────────────────────────────────────── */
export const fmt = {
    num: (v: number | null | undefined, dp = 0): string =>
        v === null || v === undefined || !Number.isFinite(v) ? '—' : (+v).toFixed(dp),
    sign: (v: number | null | undefined, dp = 0): string =>
        v === null || v === undefined || !Number.isFinite(v) ? '—' : (v >= 0 ? '+' : '') + (+v).toFixed(dp),
    lat: (v: number | null | undefined): string =>
        v === null || v === undefined ? '—' : `${(+v).toFixed(6)}°`,
    lon: (v: number | null | undefined): string =>
        v === null || v === undefined ? '—' : `${(+v).toFixed(6)}°`,
    time: (ms: number | null | undefined): string => {
        if (ms === null || ms === undefined) return '—';
        const d = new Date(ms);
        const p = (n: number) => String(n).padStart(2, '0');
        return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
    },
    datetime: (ms: number | null | undefined): string => {
        if (ms === null || ms === undefined) return '—';
        const d = new Date(ms);
        const p = (n: number) => String(n).padStart(2, '0');
        return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
    },
    duration: (ms: number | null | undefined): string => {
        if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—';
        const s = Math.floor(ms / 1000);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const ss = s % 60;
        if (h > 0) return `${h}h ${m}m`;
        if (m > 0) return `${m}m ${ss}s`;
        return `${ss}s`;
    },
};

/* ──────────────────────────────────────────────────────────────
 * Staleness — every atom with a freshness indicator runs through this.
 * ────────────────────────────────────────────────────────────── */
export type StalenessTier = 'fresh' | 'recent' | 'stale' | 'old' | 'unknown';
export interface Staleness {
    tier: StalenessTier;
    color: string;
    name: string;
}
export function staleness(t: number | null | undefined, now: number = Date.now()): Staleness {
    if (t === null || t === undefined) return { tier: 'unknown', color: 'var(--sl-text-dim3)', name: 'NEVER' };
    const age = now - t;
    if (age < 60_000)      return { tier: 'fresh',  color: 'var(--sl-ok)',    name: 'LIVE'   };
    if (age < 5 * 60_000)  return { tier: 'recent', color: 'var(--sl-ok-mute)', name: 'RECENT' };
    if (age < 15 * 60_000) return { tier: 'stale',  color: 'var(--sl-alert)', name: 'STALE'  };
    return                       { tier: 'old',    color: 'var(--sl-alert)', name: 'OLD'    };
}

export function Age({ t, now, compact, dot = true, prefix }: {
    t: number | null | undefined;
    now: number;
    compact?: boolean;
    dot?: boolean;
    prefix?: string;
}) {
    if (t === null || t === undefined) {
        return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--sl-text-dim3)' }}>
                {dot && <span className="sl-dot dim" style={{ width: 5, height: 5 }} />}
                NEVER
            </span>
        );
    }
    const s = staleness(t, now);
    const age = now - t;
    let txt: string;
    if (age < 1000) txt = 'just now';
    else if (age < 60_000) txt = `${Math.floor(age / 1000)}s ago`;
    else if (age < 3_600_000) txt = `${Math.floor(age / 60_000)}m ${Math.floor((age % 60_000) / 1000)}s ago`;
    else txt = `${Math.floor(age / 3_600_000)}h ${Math.floor((age % 3_600_000) / 60_000)}m ago`;
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: compact ? 9 : 10,
            color: s.color,
            fontFamily: 'var(--sl-mono)',
            fontVariantNumeric: 'tabular-nums',
        }}>
            {dot && <span style={{ width: 5, height: 5, background: s.color, flexShrink: 0 }} />}
            {prefix && <span style={{ color: 'var(--sl-text-dim3)', marginRight: 2 }}>{prefix}</span>}
            {txt}
        </span>
    );
}

export function FreshnessBar({ t, now, max = 5 * 60_000, width = 60 }: {
    t: number | null | undefined;
    now: number;
    max?: number;
    width?: number;
}) {
    if (t === null || t === undefined) {
        return <div style={{ width, height: 2, background: 'var(--sl-text-dim3)', opacity: 0.3 }} />;
    }
    const s = staleness(t, now);
    const age = now - t;
    const pct = Math.min(100, (age / max) * 100);
    return (
        <div style={{ width, height: 2, background: 'rgba(255,255,255,0.06)', position: 'relative' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${100 - pct}%`, background: s.color, transition: 'width 0.3s' }} />
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Panel
 * ────────────────────────────────────────────────────────────── */
export function Panel({ title, right, children, style, bodyStyle, noBody }: {
    title?: ReactNode;
    right?: ReactNode;
    children?: ReactNode;
    style?: React.CSSProperties;
    bodyStyle?: React.CSSProperties;
    noBody?: boolean;
}) {
    return (
        <div className="sl-panel" style={style}>
            {title && (
                <div className="sl-panel-h">
                    <span>{title}</span>
                    {right && <span className="right">{right}</span>}
                </div>
            )}
            {!noBody && <div className="sl-panel-body" style={bodyStyle}>{children}</div>}
            {noBody && children}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * KPI
 * ────────────────────────────────────────────────────────────── */
export function KPI({ label, value, unit, sub, subKind, accent, style }: {
    label: ReactNode;
    value: ReactNode;
    unit?: ReactNode;
    sub?: ReactNode;
    subKind?: 'up' | 'down';
    accent?: 'ok' | 'alert';
    style?: React.CSSProperties;
}) {
    const className = 'sl-kpi' + (accent ? ` accent-${accent}` : '');
    return (
        <div className={className} style={style}>
            <div className="lbl">{label}</div>
            <div className="val">
                {value}{unit && <span className="u">{unit}</span>}
            </div>
            {sub !== undefined && sub !== null && <div className={'sub' + (subKind ? ` ${subKind}` : '')}>{sub}</div>}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * KV
 * ────────────────────────────────────────────────────────────── */
export function KV({ k, v, u, accent }: {
    k: ReactNode;
    v: ReactNode;
    u?: ReactNode;
    accent?: 'teal' | 'amber' | 'dim';
}) {
    return (
        <div className="sl-kv-row">
            <span className="k">{k}</span>
            <span className={'v' + (accent ? ` ${accent}` : '')}>{v}{u && <span className="u">{u}</span>}</span>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Sparkline — accepts (number | null) so it draws a gap when the
 * firmware skipped that field on a given packet.
 * ────────────────────────────────────────────────────────────── */
export function Sparkline({
    data, width = 200, height = 28, color = 'var(--sl-ok)', fill = false,
    min, max, dots = false,
}: {
    data: Array<number | null>;
    width?: number;
    height?: number;
    color?: string;
    fill?: boolean;
    min?: number;
    max?: number;
    dots?: boolean;
}) {
    const valid = data.filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v));
    if (valid.length < 2) return <svg width={width} height={height}></svg>;
    const lo = min !== undefined ? min : Math.min(...valid);
    const hi = max !== undefined ? max : Math.max(...valid);
    const range = hi - lo || 1;
    const n = data.length;
    const points = data.map((v, i) => {
        if (v === null || v === undefined || !Number.isFinite(v)) return null;
        const x = (i / (n - 1)) * width;
        const y = height - ((v - lo) / range) * (height - 2) - 1;
        return { x, y };
    });
    let d = '';
    let started = false;
    points.forEach((p) => {
        if (p === null) { started = false; return; }
        d += (started ? ' L' : 'M') + p.x.toFixed(1) + ' ' + p.y.toFixed(1);
        started = true;
    });
    const fillD = fill && d ? d + ` L${width} ${height} L0 ${height} Z` : null;
    return (
        <svg width={width} height={height} style={{ display: 'block' }}>
            {fillD && <path d={fillD} fill={color} opacity={0.07} />}
            <path d={d} fill="none" stroke={color} strokeWidth="1.2" />
            {dots && points.map((p, i) =>
                p && (i === points.length - 1 || (i > 0 && points[i - 1] === null)) ? (
                    <circle key={i} cx={p.x} cy={p.y} r="2" fill={color} />
                ) : null,
            )}
        </svg>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chart — full chart with axis ticks, grid, optional fill area,
 * and an optional vertical scrubber.
 * ────────────────────────────────────────────────────────────── */
export function Chart<T extends { t: number }>({
    data, getY, width, height,
    color = 'var(--sl-ok)', fill = true, area = true,
    min, max,
    padL = 36, padR = 12, padT = 12, padB = 22,
    yTicks = 4,
    label, unit,
    scrubT,
    markers,
    hideAxis = false,
}: {
    data: T[];
    getY: (row: T) => number | null | undefined;
    width: number;
    height: number;
    color?: string;
    fill?: boolean;
    area?: boolean;
    min?: number;
    max?: number;
    padL?: number;
    padR?: number;
    padT?: number;
    padB?: number;
    yTicks?: number;
    label?: string;
    unit?: string;
    scrubT?: number;
    markers?: Array<{ t: number; color?: string }>;
    hideAxis?: boolean;
}) {
    const innerW = width - padL - padR;
    const innerH = height - padT - padB;
    const valid = data
        .map(d => getY(d))
        .filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v));
    if (!valid.length) return <svg width={width} height={height} />;
    const lo = min !== undefined ? min : Math.min(...valid);
    const hi = max !== undefined ? max : Math.max(...valid);
    const range = hi - lo || 1;
    const t0 = data[0].t;
    const t1 = data[data.length - 1].t;
    const tspan = t1 - t0 || 1;
    const xOf = (t: number) => padL + ((t - t0) / tspan) * innerW;
    const yOf = (v: number) => padT + innerH - ((v - lo) / range) * innerH;

    let d = '';
    let started = false;
    data.forEach((row) => {
        const v = getY(row);
        if (v === null || v === undefined || !Number.isFinite(v)) { started = false; return; }
        const x = xOf(row.t).toFixed(1);
        const y = yOf(v).toFixed(1);
        d += (started ? ' L' : 'M') + x + ' ' + y;
        started = true;
    });
    const fillD = (fill && area && d) ? d + ` L${(padL + innerW).toFixed(1)} ${(padT + innerH).toFixed(1)} L${padL} ${(padT + innerH).toFixed(1)} Z` : null;

    const yTickArr = Array.from({ length: yTicks + 1 }, (_, i) => lo + (range * i) / yTicks);

    return (
        <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
            {!hideAxis && yTickArr.map((v, i) => {
                const y = yOf(v);
                return (
                    <g key={i}>
                        <line
                            x1={padL} y1={y} x2={padL + innerW} y2={y}
                            stroke="var(--sl-grid)"
                            strokeDasharray={i === 0 || i === yTicks ? '' : '2 3'}
                        />
                        <text x={padL - 6} y={y + 3} textAnchor="end" className="sl-tick">
                            {v >= 1000 ? (v / 1000).toFixed(1) + 'k' : (Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(0))}
                        </text>
                    </g>
                );
            })}
            {label && (
                <text x={padL} y={padT - 3} className="sl-axis-label">
                    {label}{unit && <tspan dx="6" fill="var(--sl-text-dim3)">{unit}</tspan>}
                </text>
            )}
            {fillD && <path d={fillD} fill={color} opacity={0.06} />}
            <path d={d} fill="none" stroke={color} strokeWidth="1.4" />
            {!hideAxis && [0, 0.5, 1].map((f, i) => {
                const t = t0 + tspan * f;
                const x = padL + innerW * f;
                return (
                    <text
                        key={i}
                        x={x}
                        y={padT + innerH + 14}
                        textAnchor={i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}
                        className="sl-tick"
                    >
                        {fmt.time(t)}
                    </text>
                );
            })}
            {scrubT !== undefined && scrubT >= t0 && scrubT <= t1 && (
                <line x1={xOf(scrubT)} y1={padT} x2={xOf(scrubT)} y2={padT + innerH} stroke="var(--sl-ok-mute)" strokeDasharray="2 3" />
            )}
            {markers && markers.map((m, i) => (
                <line
                    key={i}
                    x1={xOf(m.t)} y1={padT}
                    x2={xOf(m.t)} y2={padT + innerH}
                    stroke={m.color || 'var(--sl-alert)'}
                    strokeOpacity="0.4"
                />
            ))}
        </svg>
    );
}

/* ──────────────────────────────────────────────────────────────
 * CadenceStrip — packet timings as vertical ticks. Gap > 90s = warn,
 * > 120s = alert.
 * ────────────────────────────────────────────────────────────── */
export function CadenceStrip({ data, width, height = 28, t0, t1 }: {
    data: TelemetryRow[];
    width: number;
    height?: number;
    t0: number;
    t1: number;
}) {
    const span = t1 - t0;
    return (
        <svg width={width} height={height} style={{ display: 'block' }}>
            <rect width={width} height={height} fill="rgba(0,0,0,0.2)" stroke="var(--sl-border)" />
            {data.map((row, i) => {
                if (row.t < t0 || row.t > t1) return null;
                const x = ((row.t - t0) / span) * width;
                const gap = i > 0 ? row.t - data[i - 1].t : 0;
                let color = 'var(--sl-ok)';
                if (gap > 120000) color = 'var(--sl-alert)';
                else if (gap > 90000) color = 'var(--sl-alert-mute)';
                return (
                    <line
                        key={i}
                        x1={x} y1={4} x2={x} y2={height - 4}
                        stroke={color}
                        strokeOpacity={0.7}
                        strokeWidth="1.2"
                    />
                );
            })}
        </svg>
    );
}

/* ──────────────────────────────────────────────────────────────
 * MapView — abstract grid + state outline + flight track. Mirrors
 * the design's stylized map (no external tiles required for v1).
 * ────────────────────────────────────────────────────────────── */
const STATE_PATHS = [
    'M 100 380 L 250 360 L 400 350 L 580 345 L 760 350 L 900 360 L 1040 365 L 1180 370 L 1320 380 L 1440 400',
    'M 100 470 L 250 460 L 400 450 L 580 450 L 760 460 L 900 465 L 1040 470 L 1180 475 L 1320 480 L 1440 500',
    'M 100 580 L 250 575 L 400 565 L 580 555 L 760 560 L 900 565 L 1040 570 L 1180 580 L 1320 595 L 1440 610',
    'M 240 350 L 250 460 L 270 575',
    'M 420 345 L 400 460 L 415 565',
    'M 580 345 L 580 450 L 580 555',
    'M 760 350 L 760 460 L 760 560',
    'M 900 360 L 900 465 L 900 565',
    'M 1040 365 L 1040 470 L 1040 570',
    'M 1180 370 L 1180 475 L 1180 580',
];

export function MapView({
    width, height,
    track,
    focus,
    viewBoxLat = [25, 55],
    viewBoxLon = [-130, -65],
    showGrid = true,
    showStates = true,
    marker,
    label,
}: {
    width: number;
    height: number;
    track?: Array<[number, number] | [null, null]>;
    focus?: { lat: number; lon: number };
    viewBoxLat?: [number, number];
    viewBoxLon?: [number, number];
    showGrid?: boolean;
    showStates?: boolean;
    marker?: Array<{ lat: number; lon: number; color?: string; label?: string }>;
    label?: string;
}) {
    const [latMin, latMax] = viewBoxLat;
    const [lonMin, lonMax] = viewBoxLon;
    const project = (lat: number, lon: number): [number, number] => {
        const x = ((lon - lonMin) / (lonMax - lonMin)) * width;
        const y = ((latMax - lat) / (latMax - latMin)) * height;
        return [x, y];
    };

    return (
        <svg width={width} height={height} style={{ display: 'block' }}>
            <rect width={width} height={height} fill="var(--sl-bg-1)" />
            {showGrid && Array.from({ length: 20 }, (_, i) => (
                <line key={'v' + i} x1={(i / 20) * width} y1="0" x2={(i / 20) * width} y2={height} stroke="var(--sl-grid)" />
            ))}
            {showGrid && Array.from({ length: 12 }, (_, i) => (
                <line key={'h' + i} x1="0" y1={(i / 12) * height} x2={width} y2={(i / 12) * height} stroke="var(--sl-grid)" />
            ))}
            {showStates && STATE_PATHS.map((d, i) => {
                const sx = width / 1600;
                const sy = height / 1000;
                const scaled = d.replace(/([ML])\s+(-?[\d.]+)\s+(-?[\d.]+)/g, (_m, cmd, x, y) =>
                    `${cmd} ${(parseFloat(x) * sx).toFixed(1)} ${(parseFloat(y) * sy).toFixed(1)}`,
                );
                return <path key={i} d={scaled} stroke="var(--sl-grid-hi)" fill="none" strokeWidth="1" />;
            })}
            {track && track.length > 1 && (() => {
                let d = '';
                let started = false;
                track.forEach(([lat, lon]) => {
                    if (lat === null || lon === null) { started = false; return; }
                    const [x, y] = project(lat, lon);
                    d += (started ? ' L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
                    started = true;
                });
                return <path d={d} stroke="var(--sl-ok-mute)" strokeWidth="1.5" fill="none" />;
            })()}
            {focus && (() => {
                const [x, y] = project(focus.lat, focus.lon);
                return (
                    <g>
                        <line x1={x - 14} y1={y} x2={x - 6} y2={y} stroke="var(--sl-ok)" strokeWidth="1" />
                        <line x1={x + 6} y1={y} x2={x + 14} y2={y} stroke="var(--sl-ok)" strokeWidth="1" />
                        <line x1={x} y1={y - 14} x2={x} y2={y - 6} stroke="var(--sl-ok)" strokeWidth="1" />
                        <line x1={x} y1={y + 6} x2={x} y2={y + 14} stroke="var(--sl-ok)" strokeWidth="1" />
                        <rect x={x - 3} y={y - 3} width="6" height="6" fill="var(--sl-ok)" />
                        {label && (
                            <text x={x + 18} y={y + 3} className="sl-tick" fill="var(--sl-ok)" style={{ fontSize: 10 }}>
                                {label}
                            </text>
                        )}
                    </g>
                );
            })()}
            {marker && marker.map((m, i) => {
                const [x, y] = project(m.lat, m.lon);
                const c = m.color || 'var(--sl-ok)';
                return (
                    <g key={i}>
                        <rect x={x - 3} y={y - 3} width="6" height="6" fill={c} />
                        {m.label && (
                            <text x={x + 10} y={y + 4} className="sl-tick" style={{ fontSize: 10, fill: 'var(--sl-text-dim)' }}>
                                {m.label}
                            </text>
                        )}
                    </g>
                );
            })}
        </svg>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chrome — top app bar with brand, tabs, freshness heartbeats.
 * Tabs each have a `path` for client-side navigation, plus an optional
 * `disabled` flag for the screens we haven't built yet.
 * ────────────────────────────────────────────────────────────── */
export interface ChromeTab {
    label: string;
    path: string;
    disabled?: boolean;
}

export function Chrome({
    tabs, activePath, onNavigate, version,
    lastUplinkT, lastFixT, now, right,
}: {
    tabs: ChromeTab[];
    activePath: string;
    onNavigate: (path: string) => void;
    version?: string;
    lastUplinkT: number | null;
    lastFixT: number | null;
    now: number;
    right?: ReactNode;
}) {
    return (
        <div className="sl-chrome">
            <div className="sl-brand">
                <span className="sl-brand-logo" aria-hidden>
                    {/* Logo 01 · Apex — Stratolink Logo Exploration */}
                    <svg width={22} height={22} viewBox="0 0 32 32" fill="none">
                        <rect x={14} y={4} width={4} height={4} fill="currentColor" />
                        <rect x={12} y={14} width={8} height={2} fill="currentColor" />
                        <rect x={9} y={19} width={14} height={2} fill="currentColor" />
                        <rect x={6} y={24} width={20} height={2} fill="currentColor" />
                    </svg>
                </span>
                STRATOLINK
                {version && <span className="ver">{version}</span>}
            </div>
            <div className="sl-tabs">
                {tabs.map(t => {
                    const isActive = t.path === activePath;
                    return (
                        <button
                            key={t.path}
                            type="button"
                            className={'tab' + (isActive ? ' active' : '')}
                            onClick={() => !t.disabled && onNavigate(t.path)}
                            disabled={t.disabled}
                            style={t.disabled ? { color: 'var(--sl-text-dim3)', cursor: 'not-allowed' } : undefined}
                            title={t.disabled ? 'Coming soon' : undefined}
                        >
                            {t.label}
                            {t.disabled && (
                                <span style={{
                                    marginLeft: 6, fontSize: 8, color: 'var(--sl-text-dim3)',
                                    letterSpacing: 0, textTransform: 'none',
                                }}>
                                    soon
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>
            <div style={{
                marginLeft: 24, display: 'flex', alignItems: 'center', gap: 14,
                paddingLeft: 18, borderLeft: '1px solid var(--sl-border)',
            }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <span style={{ fontSize: 9, color: 'var(--sl-text-dim3)', letterSpacing: '0.14em' }}>LAST UPLINK</span>
                    <Age t={lastUplinkT} now={now} dot />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <span style={{ fontSize: 9, color: 'var(--sl-text-dim3)', letterSpacing: '0.14em' }}>LAST GPS FIX</span>
                    <Age t={lastFixT} now={now} dot />
                </div>
            </div>
            {right && <div className="sl-chrome-right">{right}</div>}
        </div>
    );
}

/* The five tabs from the design. Pre-Launch and Mission Planner are gated
 * (prediction work, deferred). Mission Control / Device Tracker / Telemetry
 * Lab are live. */
export const DASHBOARD_V2_TABS: ChromeTab[] = [
    { label: 'PRE-LAUNCH',      path: '/dashboard-v2/prelaunch', disabled: true },
    { label: 'MISSION PLANNER', path: '/dashboard-v2/planner',   disabled: true },
    { label: 'MISSION CONTROL', path: '/dashboard-v2' },
    { label: 'DEVICE TRACKER',  path: '/dashboard-v2/device' },
    { label: 'WIND OUTLOOK',    path: '/dashboard-v2/wind' },
    { label: 'TELEMETRY LAB',   path: '/dashboard-v2/lab' },
];
