'use client';

import { useMemo, useState } from 'react';
import type { FlightSeries } from '@/lib/telemetry/flightSeries';
import { stamp, tlmFmt, type StatusLevel } from '@/lib/telemetry/telemetryV3Format';
import { StatusChip } from './primitives';

const C2: Record<StatusLevel, string> = {
    nominal: 'var(--t-nominal)',
    warn: 'var(--t-warn)',
    critical: 'var(--t-critical)',
};

function ds(arr: number[], n: number) {
    const N = arr.length;
    if (N <= n) return arr.map((v, i) => ({ v, src: i }));
    const out: { v: number; src: number }[] = [];
    for (let i = 0; i < n; i++) {
        const src = Math.round((i / (n - 1)) * (N - 1));
        out.push({ v: arr[src], src });
    }
    return out;
}

function clampIdx(i: number, n: number) {
    return Math.min(n - 1, Math.max(0, i));
}

function Tip({ xFrac, lines }: { xFrac: number; lines: React.ReactNode }) {
    const flip = xFrac > 0.6;
    return (
        <div
            style={{
                position: 'absolute',
                top: -6,
                left: `${(xFrac * 100).toFixed(1)}%`,
                transform: `translate(${flip ? '-100%' : '0'}, -100%)`,
                marginLeft: flip ? -6 : 6,
                pointerEvents: 'none',
                zIndex: 6,
                background: 'var(--t-tooltip-bg)',
                color: 'var(--t-tooltip-fg)',
                borderRadius: 3,
                padding: '5px 8px',
                whiteSpace: 'nowrap',
                boxShadow: '0 4px 16px rgba(0,0,0,0.28)',
            }}
        >
            {lines}
        </div>
    );
}

function boundLbl(pos: 'top' | 'bottom', text: string) {
    return {
        position: 'absolute' as const,
        right: 3,
        [pos]: 1,
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: '0.04em',
        color: 'var(--t-text-4)',
        fontVariantNumeric: 'tabular-nums' as const,
        pointerEvents: 'none' as const,
        lineHeight: 1,
    };
}

export function LineTrend({
    series,
    times,
    band,
    status,
    fmtFn,
    unit,
    height = 52,
    emphasis = 'normal',
}: {
    series: (number | null)[];
    times: number[];
    band?: [number, number] | null;
    status: StatusLevel;
    fmtFn: (v: number) => string;
    unit: string;
    height?: number;
    emphasis?: 'normal' | 'low';
}) {
    const [hover, setHover] = useState<number | null>(null);
    const numeric = series.map((v) => (v == null ? NaN : v)).filter((v) => !Number.isNaN(v));
    if (numeric.length < 2) {
        return (
            <div className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)', padding: '8px 0' }}>
                Not enough samples
            </div>
        );
    }
    const filled = series.map((v, i) => (v == null ? (numeric[0] ?? 0) : v)) as number[];
    const W = 300;
    const H = height;
    const pts = useMemo(() => ds(filled, Math.min(filled.length, 90)), [filled]);
    const dataMin = Math.min(...numeric);
    const dataMax = Math.max(...numeric);
    let lo = dataMin;
    let hi = dataMax;
    if (band) {
        lo = Math.min(lo, band[0]);
        hi = Math.max(hi, band[1]);
    }
    const pad = (hi - lo) * 0.1 || 1;
    lo -= pad;
    hi += pad;
    const span = hi - lo || 1;
    const X = (i: number) => (i / (pts.length - 1)) * W;
    const Y = (v: number) => H - ((v - lo) / span) * H;
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${X(i).toFixed(1)} ${Y(p.v).toFixed(1)}`).join(' ');
    const area = `${line} L${W} ${H} L0 ${H} Z`;
    const faint = emphasis === 'low';
    const lineCol = faint ? 'var(--t-text-4)' : 'var(--t-text-3)';
    const last = pts.length - 1;

    return (
        <div style={{ position: 'relative', width: '100%' }}>
            <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                style={{ width: '100%', height: H, display: 'block' }}
                onMouseLeave={() => setHover(null)}
                onMouseMove={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    setHover(clampIdx(Math.round(((e.clientX - r.left) / r.width) * (pts.length - 1)), pts.length));
                }}
            >
                {band &&
                    (() => {
                        const yT = Y(band[1]);
                        const yB = Y(band[0]);
                        return (
                            <g>
                                <rect x={0} y={Math.max(0, yT)} width={W} height={Math.max(1, yB - yT)} fill="var(--t-band)" />
                                <line x1={0} y1={yT} x2={W} y2={yT} stroke="var(--t-accent)" strokeWidth="0.75" strokeDasharray="3 3" opacity="0.35" />
                                <line x1={0} y1={yB} x2={W} y2={yB} stroke="var(--t-accent)" strokeWidth="0.75" strokeDasharray="3 3" opacity="0.35" />
                            </g>
                        );
                    })()}
                <path d={area} fill={lineCol} opacity={faint ? 0.05 : 0.08} />
                <path
                    d={line}
                    fill="none"
                    stroke={lineCol}
                    strokeWidth={faint ? 1 : 1.4}
                    opacity={faint ? 0.7 : 0.95}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                />
                {hover != null && <line x1={X(hover)} y1={0} x2={X(hover)} y2={H} stroke="var(--t-accent)" strokeWidth="0.75" opacity="0.5" />}
                {hover != null && <circle cx={X(hover)} cy={Y(pts[hover].v)} r="2.6" fill="var(--t-accent)" />}
                <circle cx={X(last)} cy={Y(pts[last].v)} r="3" fill={C2[status]} stroke="var(--t-panel)" strokeWidth="1.5" />
            </svg>
            <div style={boundLbl('top', fmtFn(dataMax))}>{fmtFn(dataMax)}</div>
            <div style={boundLbl('bottom', fmtFn(dataMin))}>{fmtFn(dataMin)}</div>
            {hover != null && pts[hover] && (
                <Tip
                    xFrac={X(hover) / W}
                    lines={
                        <>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                {fmtFn(pts[hover].v)}
                                <span style={{ opacity: 0.6, marginLeft: 3 }}>{unit}</span>
                            </div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.08em', opacity: 0.6, marginTop: 1 }}>
                                {stamp(times[pts[hover].src])}
                            </div>
                        </>
                    }
                />
            )}
        </div>
    );
}

export function PowerOverlay({ flight, height = 104, showBand = true }: { flight: FlightSeries; height?: number; showBand?: boolean }) {
    const [hover, setHover] = useState<number | null>(null);
    const W = 300;
    const H = height;
    const n = 90;
    const solarRaw = flight.solar.map((v) => v ?? 0);
    const battRaw = flight.batt.map((v) => v ?? 3.3);
    const sun = useMemo(() => ds(flight.sun, n), [flight.sun]);
    const solar = useMemo(() => ds(solarRaw, n), [solarRaw]);
    const batt = useMemo(() => ds(battRaw, n), [battRaw]);
    const X = (i: number) => (i / (n - 1)) * W;
    const sY = (v: number) => H - Math.min(1, Math.max(0, v / 6.2)) * H;
    const bLo = 2.9;
    const bHi = 4.25;
    const bY = (v: number) => H - ((v - bLo) / (bHi - bLo)) * H;
    const sLine = solar.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${sY(p.v).toFixed(1)}`).join(' ');
    const sArea = `${sLine} L${W} ${H} L0 ${H} Z`;
    const bLine = batt.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${bY(p.v).toFixed(1)}`).join(' ');
    const last = n - 1;

    return (
        <div style={{ position: 'relative', width: '100%' }}>
            <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                style={{ width: '100%', height: H, display: 'block' }}
                onMouseLeave={() => setHover(null)}
                onMouseMove={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    setHover(clampIdx(Math.round(((e.clientX - r.left) / r.width) * (n - 1)), n));
                }}
            >
                {sun.map((p, i) =>
                    p.v < 0.04 ? (
                        <rect key={`n${i}`} x={X(i) - W / n / 2} y={0} width={W / n + 0.5} height={H} fill="var(--t-night)" />
                    ) : null,
                )}
                {showBand && <rect x={0} y={bY(4.2)} width={W} height={Math.max(1, bY(3.6) - bY(4.2))} fill="var(--t-band)" />}
                <path d={sArea} fill="var(--t-accent)" opacity="0.13" />
                <path d={sLine} fill="none" stroke="var(--t-accent)" strokeWidth="1.1" opacity={0.7} strokeLinejoin="round" />
                <path d={bLine} fill="none" stroke="var(--t-text-2)" strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
                {hover != null && <line x1={X(hover)} y1={0} x2={X(hover)} y2={H} stroke="var(--t-accent)" strokeWidth="0.75" opacity="0.5" />}
                {hover != null && <circle cx={X(hover)} cy={bY(batt[hover].v)} r="2.4" fill="var(--t-text)" />}
                <circle cx={X(last)} cy={bY(batt[last].v)} r="3" fill="var(--t-warn)" stroke="var(--t-panel)" strokeWidth="1.5" />
            </svg>
            {hover != null && solar[hover] && (
                <Tip
                    xFrac={X(hover) / W}
                    lines={
                        <>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontVariantNumeric: 'tabular-nums', display: 'flex', gap: 10 }}>
                                <span>
                                    <span style={{ opacity: 0.55 }}>SOL </span>
                                    {solar[hover].v.toFixed(2)}V
                                </span>
                                <span>
                                    <span style={{ opacity: 0.55 }}>BAT </span>
                                    {batt[hover].v.toFixed(2)}V
                                </span>
                            </div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.08em', opacity: 0.6, marginTop: 2 }}>
                                {sun[hover].v < 0.04 ? 'NIGHT · ' : 'DAYLIGHT · '}
                                {stamp(flight.times[solar[hover].src])}
                            </div>
                        </>
                    }
                />
            )}
        </div>
    );
}

export function StateStrip({ sats, times, height = 50 }: { sats: (number | null)[]; times: number[]; height?: number }) {
    const [hover, setHover] = useState<number | null>(null);
    const W = 300;
    const H = height;
    const n = 76;
    const filled = sats.map((v) => v ?? 0);
    const pts = useMemo(() => ds(filled, n), [filled]);
    const cw = W / n;
    const stateOf = (v: number) => (v <= 0 ? 'critical' : v < 4 ? 'warn' : 'lock');
    const colOf = (s: string) => (s === 'critical' ? 'var(--t-critical)' : s === 'warn' ? 'var(--t-warn)' : 'var(--t-muted)');
    const maxS = 12;

    return (
        <div style={{ position: 'relative', width: '100%' }}>
            <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                style={{ width: '100%', height: H, display: 'block' }}
                onMouseLeave={() => setHover(null)}
                onMouseMove={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    setHover(clampIdx(Math.floor(((e.clientX - r.left) / r.width) * n), n));
                }}
            >
                {pts.map((p, i) => {
                    const s = stateOf(p.v);
                    const isNoFix = s === 'critical';
                    return (
                        <rect
                            key={i}
                            x={i * cw}
                            y={0}
                            width={cw + 0.4}
                            height={H}
                            fill={colOf(s)}
                            opacity={isNoFix ? 0.5 : s === 'warn' ? 0.42 : 0.22}
                        />
                    );
                })}
                {pts.slice(0, -1).map((p, i) => {
                    const next = pts[i + 1];
                    const x1 = i * cw + cw / 2;
                    const x2 = (i + 1) * cw + cw / 2;
                    const y1 = H - Math.min(1, p.v / maxS) * (H - 6) - 3;
                    const y2 = H - Math.min(1, next.v / maxS) * (H - 6) - 3;
                    const segState = stateOf(Math.min(p.v, next.v));
                    const segCol = segState === 'critical' ? 'var(--t-critical)' : segState === 'warn' ? 'var(--t-warn)' : 'var(--t-nominal)';
                    return (
                        <line
                            key={`l${i}`}
                            x1={x1.toFixed(1)}
                            y1={y1.toFixed(1)}
                            x2={x2.toFixed(1)}
                            y2={y2.toFixed(1)}
                            stroke={segCol}
                            strokeWidth="1.6"
                            opacity={segState === 'lock' ? 0.85 : 0.95}
                            strokeLinecap="round"
                        />
                    );
                })}
                {(() => {
                    const li = pts.findIndex((p) => p.v <= 0);
                    if (li <= 0) return null;
                    const x = li * cw + cw / 2;
                    return <line x1={x} y1={0} x2={x} y2={H} stroke="var(--t-critical)" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />;
                })()}
                <line
                    x1={0}
                    y1={H - (4 / maxS) * (H - 6) - 3}
                    x2={W}
                    y2={H - (4 / maxS) * (H - 6) - 3}
                    stroke="var(--t-text-4)"
                    strokeWidth="0.75"
                    strokeDasharray="2 3"
                />
                {hover != null && <line x1={hover * cw + cw / 2} y1={0} x2={hover * cw + cw / 2} y2={H} stroke="var(--t-accent)" strokeWidth="0.75" opacity="0.6" />}
            </svg>
            <div style={{ position: 'absolute', left: 4, top: 3, fontFamily: 'var(--font-mono)', fontSize: 8.5, letterSpacing: '0.12em', color: 'var(--t-text-4)', pointerEvents: 'none' }}>
                LOCK ≥4
            </div>
            {hover != null &&
                pts[hover] &&
                (() => {
                    const s = stateOf(pts[hover].v);
                    const lbl = s === 'critical' ? 'NO FIX' : s === 'warn' ? 'MARGINAL' : 'LOCK';
                    return (
                        <Tip
                            xFrac={(hover * cw + cw / 2) / W}
                            lines={
                                <>
                                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>
                                        {pts[hover].v} sats <span style={{ opacity: 0.6, marginLeft: 2 }}>· {lbl}</span>
                                    </div>
                                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.08em', opacity: 0.6, marginTop: 1 }}>
                                        {stamp(times[pts[hover].src])}
                                    </div>
                                </>
                            }
                        />
                    );
                })()}
        </div>
    );
}

function TrendArrow({ dir, color }: { dir: 'flat' | 'up' | 'down'; color: string }) {
    if (dir === 'flat') {
        return (
            <svg width="9" height="9" viewBox="0 0 9 9">
                <rect x="1" y="3.6" width="7" height="1.6" rx="0.8" fill={color} />
            </svg>
        );
    }
    if (dir === 'up') {
        return (
            <svg width="9" height="9" viewBox="0 0 9 9">
                <path d="M4.5 1 L8 7.5 L1 7.5 Z" fill={color} />
            </svg>
        );
    }
    return (
        <svg width="9" height="9" viewBox="0 0 9 9">
            <path d="M4.5 8 L1 1.5 L8 1.5 Z" fill={color} />
        </svg>
    );
}

export function SignalTrendRow({
    label,
    unit,
    value,
    series,
    target,
    dir,
    fmtFn,
    recent = 30,
}: {
    label: string;
    unit: string;
    value: string;
    series: (number | null)[];
    target: number;
    dir: 'high' | 'low';
    fmtFn: (v: number) => string;
    recent?: number;
}) {
    const W = 300;
    const H = 40;
    const tail = useMemo(() => series.slice(-recent).filter((v): v is number => v != null), [series, recent]);
    const [hover, setHover] = useState<number | null>(null);
    if (tail.length < 2) {
        return <div className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)', padding: '8px 0' }}>—</div>;
    }
    const dataLo = Math.min(...tail);
    const dataHi = Math.max(...tail);
    let a = Math.min(dataLo, target);
    let b = Math.max(dataHi, target);
    const pad = (b - a) * 0.18 || 1;
    a -= pad;
    b += pad;
    const span = b - a || 1;
    const X = (i: number) => (i / (tail.length - 1)) * W;
    const Y = (v: number) => H - ((v - a) / span) * H;
    const line = tail.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
    const slope = tail[tail.length - 1] - tail[0];
    const flat = Math.abs(slope) < span * 0.1;
    const improving = dir === 'high' ? slope > 0 : slope < 0;
    const tDir = flat ? 'flat' : improving ? 'up' : 'down';
    const tWord = flat ? 'Holding' : improving ? 'Improving' : 'Worsening';
    const tCol = flat ? 'var(--t-text-3)' : improving ? 'var(--t-nominal)' : 'var(--t-warn)';
    const cur = tail[tail.length - 1];
    const meets = dir === 'high' ? cur >= target : cur <= target;
    const dotCol = meets ? 'var(--t-nominal)' : 'var(--t-warn)';
    const yT = Y(target);
    const goodTop = dir === 'high' ? 0 : yT;
    const goodH = dir === 'high' ? yT : H - yT;

    return (
        <div style={{ padding: '13px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap', minWidth: 0 }}>
                    <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                        {label}
                    </span>
                    <span className="eyebrow" style={{ color: 'var(--t-text-4)', fontSize: 9 }}>
                        {unit}
                    </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <TrendArrow dir={tDir} color={tCol} />
                        <span className="eyebrow" style={{ fontSize: 9, color: tCol, fontWeight: 600 }}>
                            {tWord}
                        </span>
                    </span>
                    <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--t-text-2)', fontVariantNumeric: 'tabular-nums' }}>
                        {value}
                    </span>
                </div>
            </div>
            <div style={{ position: 'relative', width: '100%' }}>
                <svg
                    viewBox={`0 0 ${W} ${H}`}
                    preserveAspectRatio="none"
                    style={{ width: '100%', height: H, display: 'block' }}
                    onMouseLeave={() => setHover(null)}
                    onMouseMove={(e) => {
                        const r = e.currentTarget.getBoundingClientRect();
                        setHover(
                            Math.min(
                                tail.length - 1,
                                Math.max(0, Math.round(((e.clientX - r.left) / r.width) * (tail.length - 1))),
                            ),
                        );
                    }}
                >
                    <rect x={0} y={goodTop} width={W} height={Math.max(0, goodH)} fill="var(--t-nominal-soft)" opacity="0.5" />
                    <line x1={0} y1={yT} x2={W} y2={yT} stroke="var(--t-nominal)" strokeWidth="0.75" strokeDasharray="3 3" opacity="0.55" />
                    <path d={line} fill="none" stroke="var(--t-text-3)" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
                    {hover != null && <line x1={X(hover)} y1={0} x2={X(hover)} y2={H} stroke="var(--t-accent)" strokeWidth="0.75" opacity="0.5" />}
                    {hover != null && <circle cx={X(hover)} cy={Y(tail[hover])} r="2.4" fill="var(--t-accent)" />}
                    <circle cx={X(tail.length - 1)} cy={Y(cur)} r="3" fill={dotCol} stroke="var(--t-panel)" strokeWidth="1.5" />
                </svg>
                <div
                    style={{
                        position: 'absolute',
                        right: 3,
                        top: Math.max(0, yT - 12),
                        fontFamily: 'var(--font-mono)',
                        fontSize: 8.5,
                        color: 'var(--t-nominal)',
                        opacity: 0.85,
                        pointerEvents: 'none',
                        background: 'var(--t-panel)',
                        padding: '0 2px',
                    }}
                >
                    target {fmtFn(target)}
                </div>
            </div>
        </div>
    );
}

export { tlmFmt };
