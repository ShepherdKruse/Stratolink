'use client';

import type { StatusLevel } from '@/lib/telemetry/telemetryV3Format';

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

export function TrendDelta({ delta, unit, window }: { delta: number; unit: string; window: string }) {
    const flat = Math.abs(delta) < 1;
    const dir = flat ? 'flat' : delta > 0 ? 'up' : 'down';
    const col = flat ? 'var(--t-text-3)' : 'var(--t-text-2)';
    const txt = flat ? 'Stable' : `${delta > 0 ? '+' : '−'}${Math.abs(delta)} ${unit}`;
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <TrendArrow dir={dir} color={col} />
            <span className="mono" style={{ fontSize: 10.5, color: col, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                {txt}
            </span>
            {window && <span className="mono" style={{ fontSize: 10, color: 'var(--t-text-4)' }}>/ {window}</span>}
        </span>
    );
}

const CARD = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
function cardinal(deg: number) {
    return CARD[Math.round(deg / 22.5) % 16];
}

export function HeadingCompass({ heading, speed }: { heading: number | null; speed: number | null }) {
    if (heading == null) {
        return <div className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)' }}>No heading data</div>;
    }
    const h = heading;
    const sp = speed ?? 0;
    const S = 104;
    const cx = 52;
    const cy = 52;
    const r = 46;
    const ticks: [string, number][] = [
        ['N', 0],
        ['E', 90],
        ['S', 180],
        ['W', 270],
    ];
    const a = (h * Math.PI) / 180;
    const tipX = cx + Math.sin(a) * (r - 7);
    const tipY = cy - Math.cos(a) * (r - 7);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <svg width={S} height={S} viewBox={`0 0 ${S} ${S}`} style={{ flexShrink: 0 }}>
                <circle cx={cx} cy={cy} r={r} fill="var(--t-panel-2)" stroke="var(--t-border)" strokeWidth="1" />
                <circle cx={cx} cy={cy} r={r - 8} fill="none" stroke="var(--t-hairline)" strokeWidth="1" />
                {[...Array(24)].map((_, i) => {
                    const t = ((i * 15) * Math.PI) / 180;
                    const major = i % 6 === 0;
                    return (
                        <line
                            key={i}
                            x1={cx + Math.sin(t) * (r - 2)}
                            y1={cy - Math.cos(t) * (r - 2)}
                            x2={cx + Math.sin(t) * (r - (major ? 7 : 4))}
                            y2={cy - Math.cos(t) * (r - (major ? 7 : 4))}
                            stroke="var(--t-text-4)"
                            strokeWidth={major ? 1.3 : 0.8}
                        />
                    );
                })}
                {ticks.map(([lbl, deg]) => {
                    const t = (deg * Math.PI) / 180;
                    return (
                        <text
                            key={lbl}
                            x={cx + Math.sin(t) * (r - 15)}
                            y={cy - Math.cos(t) * (r - 15) + 3.5}
                            textAnchor="middle"
                            fontSize="9.5"
                            fontFamily="var(--font-mono)"
                            fill={lbl === 'N' ? 'var(--t-text-2)' : 'var(--t-text-3)'}
                            fontWeight={lbl === 'N' ? 700 : 500}
                        >
                            {lbl}
                        </text>
                    );
                })}
                <g transform={`rotate(${h} ${cx} ${cy})`}>
                    <path
                        d={`M${cx} ${cy - (r - 7)} L${cx - 6} ${cy - 14} L${cx} ${cy - 18} L${cx + 6} ${cy - 14} Z`}
                        fill="var(--t-accent)"
                    />
                    <line x1={cx} y1={cy} x2={cx} y2={cy - 14} stroke="var(--t-accent)" strokeWidth="2" opacity="0.45" />
                    <path d={`M${cx} ${cy + 12} L${cx - 4} ${cy} L${cx + 4} ${cy} Z`} fill="var(--t-text-4)" opacity="0.6" />
                </g>
                <circle className="live-dot" cx={tipX} cy={tipY} r="3.5" fill="var(--t-accent)" />
                <circle cx={cx} cy={cy} r="3" fill="var(--t-text-2)" />
            </svg>
            <div style={{ minWidth: 0 }}>
                <div className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9, marginBottom: 6 }}>
                    Ground track
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                    <span className="disp" style={{ fontSize: 30, fontWeight: 600, color: 'var(--t-text)', letterSpacing: '-0.02em', lineHeight: 0.9 }}>
                        {cardinal(h)}
                    </span>
                    <span className="mono" style={{ fontSize: 13, color: 'var(--t-text-3)' }}>
                        {Math.round(h)}°
                    </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 8 }}>
                    <span className="disp mono" style={{ fontSize: 20, fontWeight: 600, color: 'var(--t-accent)', letterSpacing: '-0.01em', lineHeight: 1 }}>
                        {Math.round(sp)}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)' }}>
                        km/h
                    </span>
                </div>
            </div>
        </div>
    );
}

export function AscentRate({ rate }: { rate: number | null }) {
    const r = rate ?? 0;
    const lo = -1;
    const hi = 1;
    const pct = (v: number) => ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * 100;
    const inBand = Math.abs(r) <= 0.5;
    const col = inBand ? 'var(--t-nominal)' : 'var(--t-warn)';
    const word = r < -0.05 ? 'Float descent' : r > 0.05 ? 'Float climb' : 'Holding';
    return (
        <div style={{ padding: '13px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9, gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
                    <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                        Ascent rate
                    </span>
                    <span className="eyebrow" style={{ color: 'var(--t-text-4)', fontSize: 9 }}>
                        m/s
                    </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <span className="disp mono" style={{ fontSize: 18, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.01em', color: 'var(--t-text)' }}>
                        {r.toFixed(1)}
                    </span>
                    <span
                        className="eyebrow"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 5,
                            padding: '2px 7px 2px 6px',
                            fontSize: 9,
                            whiteSpace: 'nowrap',
                            color: col,
                            background: inBand ? 'var(--t-nominal-soft)' : 'var(--t-warn-soft)',
                            border: `1px solid ${col}`,
                            borderRadius: 2,
                        }}
                    >
                        <span style={{ width: 5, height: 5, borderRadius: '50%', background: col }} />
                        {word}
                    </span>
                </div>
            </div>
            <div style={{ position: 'relative', height: 16 }}>
                <div style={{ position: 'absolute', top: 5, left: 0, right: 0, height: 6, borderRadius: 3, background: 'var(--t-panel-2)', border: '1px solid var(--t-border)' }} />
                <div
                    style={{
                        position: 'absolute',
                        top: 5,
                        left: `${pct(-0.5)}%`,
                        width: `${pct(0.5) - pct(-0.5)}%`,
                        height: 6,
                        background: 'var(--t-nominal-soft)',
                        borderLeft: '1px solid var(--t-nominal)',
                        borderRight: '1px solid var(--t-nominal)',
                    }}
                />
                <div style={{ position: 'absolute', top: '50%', left: `${pct(r)}%`, width: 10, height: 10, borderRadius: '50%', background: col, border: '2px solid var(--t-panel)', transform: 'translate(-50%,-50%)' }} />
            </div>
        </div>
    );
}

export function SignalQuality({
    rssi,
    snr,
    gateways,
    gwTotal,
}: {
    rssi: number | null;
    snr: number | null;
    gateways: number;
    gwTotal: number;
}) {
    const r = rssi ?? -120;
    const s = snr ?? -6;
    const rScore = Math.min(1, Math.max(0, (r + 120) / 27));
    const sScore = Math.min(1, Math.max(0, (s + 6) / 16));
    const blend = rScore * 0.6 + sScore * 0.4;
    const bars = Math.max(0, Math.min(5, Math.round(blend * 5)));
    const status: StatusLevel = bars <= 1 ? 'critical' : bars === 2 ? 'warn' : bars >= 4 ? 'nominal' : 'warn';
    const label = ['No link', 'Very weak', 'Weak', 'Fair', 'Strong', 'Excellent'][bars];
    const col = status === 'critical' ? 'var(--t-critical)' : status === 'warn' ? 'var(--t-warn)' : 'var(--t-nominal)';
    const heights = [7, 11, 15, 19, 23];
    return (
        <div style={{ padding: '13px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                    Link quality
                </span>
                <span className="disp" style={{ fontSize: 16, fontWeight: 600, color: col, letterSpacing: '-0.01em' }}>
                    {label}
                </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <svg width="40" height="26" viewBox="0 0 40 26" style={{ flexShrink: 0 }}>
                    {heights.map((h, i) => (
                        <rect key={i} x={i * 8} y={25 - h} width="5.5" height={h} rx="1" fill={i < bars ? col : 'var(--t-muted)'} opacity={i < bars ? 1 : 0.45} />
                    ))}
                </svg>
                <div style={{ minWidth: 0 }}>
                    <div className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9, marginBottom: 3 }}>
                        Gateways
                    </div>
                    <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--t-text)', fontVariantNumeric: 'tabular-nums' }}>
                        {gateways}
                        <span style={{ color: 'var(--t-text-3)' }}> / {gwTotal}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

export function PowerFlow({ solarV, battV }: { solarV: number | null; battV: number | null }) {
    const solar = solarV ?? 0;
    const batt = battV ?? 3.3;
    const charging = solar > batt + 0.05;
    const soc = Math.round(Math.min(100, Math.max(0, ((batt - 3.0) / (4.2 - 3.0)) * 100)));
    const battStatus: StatusLevel = soc < 12 ? 'critical' : soc < 35 ? 'warn' : 'nominal';
    const battCol = battStatus === 'critical' ? 'var(--t-critical)' : battStatus === 'warn' ? 'var(--t-warn)' : 'var(--t-nominal)';
    const sun = (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
        </svg>
    );
    const chip = (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <rect x="6" y="6" width="12" height="12" rx="1" />
            <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" />
        </svg>
    );
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 4 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: 50, flexShrink: 0, opacity: charging ? 1 : 0.4 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--t-panel-2)', border: '1px solid var(--t-border)', color: 'var(--t-text-2)' }}>{sun}</div>
                    <span className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 8 }}>Solar</span>
                    <span className="mono" style={{ fontSize: 10, color: 'var(--t-text-2)' }}>{solar.toFixed(2)} V</span>
                </div>
                <div style={{ flex: 1, minWidth: 22, position: 'relative', height: 24, alignSelf: 'flex-start', marginTop: 12 }}>
                    {charging && [0, 1, 2].map((i) => (
                        <span key={i} className="flow-dot" style={{ background: 'var(--t-nominal)', animationDelay: `${i * 0.53}s` }} />
                    ))}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: 96, flexShrink: 0 }}>
                    <svg width="46" height="24" viewBox="0 0 46 24">
                        <rect x="1" y="4" width="40" height="16" rx="2.5" fill="var(--t-panel-2)" stroke="var(--t-border-2)" strokeWidth="1.2" />
                        <rect x="42.5" y="9" width="3" height="6" rx="1" fill="var(--t-border-2)" />
                        <rect x="3.5" y="6.5" width={Math.max(2, 35 * (soc / 100))} height="11" rx="1.5" fill={battCol} />
                    </svg>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600, color: battCol, letterSpacing: '-0.01em', lineHeight: 1 }}>
                            {soc}%
                        </span>
                        <span className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)' }}>
                            {batt.toFixed(2)} V
                        </span>
                    </div>
                </div>
                <div style={{ flex: 1, minWidth: 22, position: 'relative', height: 24, alignSelf: 'flex-start', marginTop: 12 }}>
                    <span className="flow-dot" style={{ background: charging ? 'var(--t-nominal)' : 'var(--t-warn)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, width: 50, flexShrink: 0 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--t-panel-2)', border: '1px solid var(--t-border)', color: 'var(--t-text-2)' }}>{chip}</div>
                    <span className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 8 }}>Payload</span>
                    <span className="mono" style={{ fontSize: 10, color: 'var(--t-text-2)' }}>TX</span>
                </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
                <span
                    className="eyebrow"
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 5,
                        padding: '3px 8px 3px 7px',
                        fontSize: 9,
                        whiteSpace: 'nowrap',
                        color: charging ? 'var(--t-nominal)' : 'var(--t-warn)',
                        background: charging ? 'var(--t-nominal-soft)' : 'var(--t-warn-soft)',
                        border: `1px solid ${charging ? 'var(--t-nominal)' : 'var(--t-warn)'}`,
                        borderRadius: 2,
                    }}
                >
                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: charging ? 'var(--t-nominal)' : 'var(--t-warn)' }} />
                    {charging ? 'Charging' : 'Discharging'}
                </span>
            </div>
        </div>
    );
}

export function AttitudeBubble({ tilt, sway }: { tilt: number | null; sway: number | null }) {
    const t = tilt ?? 0;
    const s = sway ?? 0;
    const cx = 38;
    const cy = 38;
    const R = 33;
    const status: StatusLevel = t < 12 ? 'nominal' : t < 22 ? 'warn' : 'critical';
    const col = status === 'nominal' ? 'var(--t-nominal)' : status === 'warn' ? 'var(--t-warn)' : 'var(--t-critical)';
    const word = t < 12 ? 'Steady' : t < 22 ? 'Swinging' : 'Tumbling';
    const off = Math.min(1, t / 30) * (R - 9);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <svg width="76" height="76" viewBox="0 0 76 76" style={{ flexShrink: 0 }}>
                <circle cx={cx} cy={cy} r={R} fill="var(--t-panel-2)" stroke="var(--t-border)" strokeWidth="1" />
                <g className="att-sway" style={{ transformOrigin: '38px 38px' }}>
                    <circle cx={cx} cy={cy - off} r="6" fill={col} opacity="0.9" />
                </g>
            </svg>
            <div>
                <div className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9, marginBottom: 5 }}>
                    Attitude
                </div>
                <div className="disp" style={{ fontSize: 18, fontWeight: 600, color: col, letterSpacing: '-0.01em' }}>
                    {word}
                </div>
                <div className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-3)', marginTop: 3 }}>
                    {Math.round(t)}° tilt · {Math.round(s)}° sway
                </div>
            </div>
        </div>
    );
}

export function DaylightMeter({ lux }: { lux: number | null }) {
    const L = lux ?? 0;
    const part = L < 50 ? 'Night' : L < 2000 ? 'Dusk' : L < 20000 ? 'Low sun' : 'Full sun';
    const phase = Math.min(1, L / 96000);
    const pct = (phase * 100).toFixed(1);
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                    Ambient light
                </span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-2)', whiteSpace: 'nowrap' }}>
                    {part} · {L.toLocaleString()} lux
                </span>
            </div>
            <div
                style={{
                    position: 'relative',
                    height: 16,
                    borderRadius: 99,
                    overflow: 'hidden',
                    border: '1px solid var(--t-border)',
                    background: 'linear-gradient(90deg, #1B2330 0%, #46505E 14%, #C9A24B 27%, #F0DCA0 50%, #C9A24B 73%, #46505E 86%, #1B2330 100%)',
                }}
            >
                <div
                    style={{
                        position: 'absolute',
                        left: `${pct}%`,
                        top: '50%',
                        width: 12,
                        height: 12,
                        borderRadius: '50%',
                        background: '#FFF',
                        border: '2px solid #11161D',
                        transform: 'translate(-50%,-50%)',
                    }}
                />
            </div>
        </div>
    );
}

function KV({ label, value, tone }: { label: string; value: string; tone?: StatusLevel }) {
    return (
        <div style={{ minWidth: 0 }}>
            <div className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9, marginBottom: 3, whiteSpace: 'nowrap' }}>
                {label}
            </div>
            <div
                className="mono"
                style={{
                    fontSize: 12,
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    color: tone === 'critical' ? 'var(--t-critical)' : tone === 'warn' ? 'var(--t-warn)' : 'var(--t-text-2)',
                }}
            >
                {value}
            </div>
        </div>
    );
}

export function GpsKvRow({ noFixMs, lastFixStamp }: { noFixMs: number | null; lastFixStamp: string }) {
    return (
        <div style={{ display: 'flex', gap: 20, marginTop: 11 }}>
            <KV label="No lock" value={noFixMs != null ? relTimeShort(noFixMs) : '—'} tone={noFixMs != null ? 'critical' : undefined} />
            <KV label="Last fix" value={lastFixStamp} />
        </div>
    );
}

function relTimeShort(ms: number): string {
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}
