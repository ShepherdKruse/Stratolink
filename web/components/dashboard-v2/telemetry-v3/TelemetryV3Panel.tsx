'use client';

import Image from 'next/image';
import { useEffect, useMemo, useState } from 'react';
import { fmt, type TelemetryRow } from '@/components/dashboard-v2/atoms';
import type { DeviceSummary } from '@/components/dashboard-v2/useTelemetry';
import {
    buildFlightSeries,
    computePayloadAttitude,
    last,
} from '@/lib/telemetry/flightSeries';
import { relTime, stamp, tlmFmt, type StatusLevel } from '@/lib/telemetry/telemetryV3Format';
import { useGatewayPoints } from '@/lib/gateways/data';
import { haversineKm } from '@/lib/gateways/range';
import { LineTrend } from './charts';
import ThemeToggle from '@/components/dashboard-v2/ThemeToggle';
import { Divider, DOT, Group } from './primitives';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "May 17, 2026 · 15:55 UTC" — no seconds, friendlier than the raw stamp. */
function fmtLaunch(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()} · ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

type FlightSummary = { durationMs: number | null; distanceKm: number };

export type TelemetryV3PanelProps = {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    summary: FlightSummary;
    rows: TelemetryRow[];
    /** True when there's no live reading at the cursor — out in the forecast,
     *  or sitting in a transmission gap. Point-in-time readings are blanked. */
    isFuture?: boolean;
    /** Controls which slices of the panel render. 'full' (default, desktop)
     *  shows everything. On mobile the panel is split: 'summary' is the
     *  always-visible top block (brand, device, top-level metrics, link
     *  status) and 'charts' is the pull-up drawer (chart sections + footer,
     *  no header). */
    variant?: 'full' | 'summary' | 'charts';
};

/** Live-updating "time since last contact", value only (for a key metric). */
function LastContactValue({ lastContactT }: { lastContactT: number | null }) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 3000);
        return () => clearInterval(id);
    }, []);
    if (lastContactT == null) return <>—</>;
    return <>{relTime(Math.max(0, now - lastContactT))}</>;
}

/** Header status — a quiet dot + label, not a button/chip. */
function HeaderStatus({ status, label }: { status: StatusLevel; label: string }) {
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: DOT[status], flexShrink: 0 }} />
            <span className="eyebrow" style={{ color: 'var(--t-text-2)', fontSize: 9.5 }}>{label}</span>
        </span>
    );
}

/** Link status tied to the chart: green "Transmitting" when the cursor sits on
 *  real telemetry, red "No Connection" in a gap or out past the last packet. */
function ConnectionStatus({ connected }: { connected: boolean }) {
    return <HeaderStatus status={connected ? 'nominal' : 'critical'} label={connected ? 'Transmitting' : 'No Connection'} />;
}

/** A single key metric, shown plainly (no box): small label over a big value,
 * optionally preceded by a small icon. */
function Metric({ label, value, unit, icon }: { label: string; value: React.ReactNode; unit?: string; icon?: React.ReactNode }) {
    return (
        <div style={{ minWidth: 0 }}>
            <div className="eyebrow" style={{ color: 'var(--t-text-3)', marginBottom: 5, fontSize: 9, whiteSpace: 'nowrap' }}>
                {label}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {icon}
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span className="disp mono" style={{ fontSize: 19, fontWeight: 600, color: 'var(--t-text)', letterSpacing: '-0.01em', lineHeight: 1, whiteSpace: 'nowrap' }}>
                        {value}
                    </span>
                    {unit && <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)' }}>{unit}</span>}
                </div>
            </div>
        </div>
    );
}

/** Small battery glyph whose fill reflects state of charge. */
function BatteryIcon({ soc, color }: { soc: number; color: string }) {
    return (
        <svg width="23" height="12" viewBox="0 0 24 12" style={{ flexShrink: 0 }}>
            <rect x="0.6" y="1.2" width="20" height="9.6" rx="1.8" fill="none" stroke="var(--t-border-2)" strokeWidth="1.1" />
            <rect x="21.2" y="4" width="2.2" height="4" rx="0.7" fill="var(--t-border-2)" />
            <rect x="2" y="2.6" width={Math.max(1.5, 17 * (Math.max(0, Math.min(100, soc)) / 100))} height="6.8" rx="1" fill={color} />
        </svg>
    );
}

/** Sun (warming with brightness) by day, moon at night — relates lux to phase. */
function DaylightIcon({ lux }: { lux: number }) {
    if (lux < 10) {
        return (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t-text-3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" />
            </svg>
        );
    }
    const col = lux < 200 ? '#5C6B7A' : lux < 5000 ? '#9A7B3C' : lux < 25000 ? '#C9922E' : '#E8B020';
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={col} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
        </svg>
    );
}

/** Small solar-panel glyph — amber when the array is generating. */
function SolarIcon({ color }: { color: string }) {
    return (
        <svg width="15" height="13" viewBox="0 0 24 20" fill="none" stroke={color} strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M3.5 15 L7 4 H21 L19 15 Z" strokeWidth="1.4" />
            <path d="M5.3 11.4 H19.4 M8.3 4 L7 15 M13 4 L12.2 15 M17.7 4 L17 15" strokeWidth="0.9" />
        </svg>
    );
}

/** Tiny payload-tilt indicator: a mast leaning from vertical by `deg`. */
function TiltIcon({ deg, color }: { deg: number; color: string }) {
    const d = Math.max(-80, Math.min(80, deg));
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
            <line x1="12" y1="3" x2="12" y2="21" stroke="var(--t-text-4)" strokeWidth="1" strokeDasharray="2 2" />
            <g transform={`rotate(${d} 12 21)`}>
                <line x1="12" y1="21" x2="12" y2="5" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
                <circle cx="12" cy="5" r="2.8" fill={color} />
            </g>
        </svg>
    );
}

export default function TelemetryV3Panel({ device, devices, onSelect, scrubRow, summary, rows, isFuture = false, variant = 'full' }: TelemetryV3PanelProps) {
    const showHeader = variant !== 'charts';
    const showBody = variant !== 'summary';
    /* The mobile summary header is tightened vertically — it's the only thing
     * visible above the map, so it earns its space. */
    const compact = variant === 'summary';
    const flight = useMemo(() => buildFlightSeries(rows), [rows]);

    /* Point-in-time readings: blanked when scrubbed past the last transmission
     * (there's no telemetry out in the forecast). */
    const row = isFuture ? null : scrubRow;
    const altVal = row?.presAlt;
    const batt = row?.batt;
    const solar = row?.sol;
    const lux = row ? (row.lux ?? last(flight.lux) ?? null) : null;
    const soc = batt != null ? Math.round(Math.min(100, Math.max(0, ((batt - 3.0) / (4.2 - 3.0)) * 100))) : null;
    const battCol = soc == null ? 'var(--t-text-3)' : soc < 12 ? 'var(--t-critical)' : soc < 35 ? 'var(--t-warn)' : 'var(--t-nominal)';
    const rssi = row?.rssi;
    const snr = row?.snr;
    const gwNow = row ? (row.gateways?.length ?? last(flight.gw) ?? 0) : null;

    /* How many known gateways are within a fixed 150 km radius of the balloon's
     * current position (matches the 150 km coverage rings on the map). */
    const gatewayPoints = useGatewayPoints();
    const gwVisible = useMemo(() => {
        const la = row?.lat ?? null;
        const lo = row?.lon ?? null;
        if (la == null || lo == null || !gatewayPoints.length) return null;
        let n = 0;
        for (const g of gatewayPoints) if (haversineKm(la, lo, g.lat, g.lon) <= 150) n++;
        return n;
    }, [row, gatewayPoints]);

    const payloadAttitude = useMemo(
        () => (row ? computePayloadAttitude(row.ax, row.ay, row.az) : null),
        [row],
    );
    const tilt = payloadAttitude?.tiltDeg ?? null;
    const tiltReliable = payloadAttitude?.reliable ?? false;
    const tiltCol = tilt == null || !tiltReliable ? 'var(--t-text-3)' : tilt < 15 ? 'var(--t-nominal)' : tilt < 35 ? 'var(--t-warn)' : 'var(--t-critical)';


    const altStatus: StatusLevel =
        altVal == null ? 'critical' : altVal >= 8500 && altVal <= 12000 ? 'nominal' : 'warn';

    if (rows.length < 2) {
        return (
            <div style={{ padding: 24, color: 'var(--t-text-3)', fontSize: 12 }} className="mono">
                Awaiting telemetry packets…
            </div>
        );
    }

    return (
        <>
            {showHeader && (
            <div style={{ borderBottom: '1px solid var(--t-border)', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: compact ? '11px 18px 0' : '15px 18px 0' }}>
                    <a href="/" className="tlm-brand-link" style={{ display: 'flex', flexShrink: 0, textDecoration: 'none' }}>
                        <Image
                            src="/stratolink-header-logo.png"
                            alt="Stratolink"
                            width={200}
                            height={40}
                            className="tlm-brand-logo"
                            priority
                        />
                    </a>
                    <span style={{ marginLeft: 'auto' }}>
                        <ThemeToggle />
                    </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: compact ? '9px 18px 0' : '14px 18px 0' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="eyebrow" style={{ color: 'var(--t-text-3)', marginBottom: compact ? 3 : 6 }}>
                            Monitoring
                        </div>
                        {/* Custom trigger (big name + caret) with a transparent
                          * native <select> overlaid — gives a clean, consistent
                          * look across browsers while keeping the native dropdown
                          * (and its normal-sized option list). */}
                        <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 7, maxWidth: '100%' }}>
                            <span className="disp" style={{ fontSize: compact ? 20 : 24, fontWeight: 600, color: 'var(--t-text)', lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {device?.callsign ?? device?.id ?? '—'}
                            </span>
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--t-text-3)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }} aria-hidden>
                                <polyline points="6 9 12 15 18 9" />
                            </svg>
                            <select
                                value={device?.id ?? ''}
                                onChange={(e) => onSelect(e.target.value)}
                                aria-label="Select balloon"
                                style={{
                                    position: 'absolute',
                                    inset: 0,
                                    width: '100%',
                                    height: '100%',
                                    opacity: 0,
                                    cursor: 'pointer',
                                    fontSize: 14,
                                    border: 'none',
                                    appearance: 'none',
                                    WebkitAppearance: 'none',
                                }}
                            >
                                {devices.map((d) => (
                                    <option key={d.id} value={d.id}>
                                        {d.callsign ?? d.id}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {device?.callsign && (
                            <div className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)', marginTop: 2 }}>
                                {device.id}
                            </div>
                        )}
                    </div>
                </div>
                <div style={{ padding: compact ? '8px 18px 0' : '12px 18px 0', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    {device?.status && (
                        <>
                            <HeaderStatus status="nominal" label={String(device.status)} />
                            <span style={{ color: 'var(--t-text-4)', fontSize: 10 }}>•</span>
                        </>
                    )}
                    <span className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-3)' }}>
                        {device?.launchedAt ? `Launched ${fmtLaunch(device.launchedAt)}` : 'Not launched'}
                    </span>
                </div>
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(72px, 1fr))',
                        gap: compact ? '10px 18px' : '16px 18px',
                        padding: compact ? '11px 18px 10px' : '16px 18px 12px',
                    }}
                >
                    <Metric label="Flight time" value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '—'} />
                    <Metric label="Total dist" value={Math.round(summary.distanceKm).toLocaleString('en-US')} unit="km" />
                    <Metric label="Last contact" value={<LastContactValue lastContactT={device?.lastContactT ?? null} />} />
                </div>
                <div style={{ padding: compact ? '0 18px 12px' : '0 18px 16px' }}>
                    <ConnectionStatus connected={!isFuture} />
                </div>
            </div>
            )}

            {showBody && (
            <>
            <Group
                index="01"
                title="Flight path"
                gkey="flight"
            >
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            Altitude <span style={{ color: 'var(--t-text-4)', fontSize: 9 }}>pres</span>
                        </span>
                        <span style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
                            {row?.pres != null && (
                                <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)', fontVariantNumeric: 'tabular-nums' }}>
                                    {tlmFmt.d1(row.pres)} hPa
                                </span>
                            )}
                            <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                                {altVal != null ? tlmFmt.int(altVal) : '—'}
                                {altVal != null && <span className="mono" style={{ fontSize: 11, fontWeight: 500, color: 'var(--t-text-3)', marginLeft: 3 }}>m</span>}
                            </span>
                        </span>
                    </div>
                    <LineTrend
                        series={flight.altPres}
                        times={flight.times}
                        band={[8500, 12000]}
                        status={altStatus}
                        fmtFn={(v) => tlmFmt.int(v)}
                        unit="m"
                        height={58}
                        scrubT={scrubRow?.t ?? null}
                    />
                </div>
                <Divider />
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            Temperature
                        </span>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                            {row?.temp != null ? tlmFmt.d1(row.temp) : '—'}
                            {row?.temp != null && <span className="mono" style={{ fontSize: 11, fontWeight: 500, color: 'var(--t-text-3)', marginLeft: 3 }}>°C</span>}
                        </span>
                    </div>
                    <LineTrend series={flight.temp} times={flight.times} status="nominal" fmtFn={(v) => tlmFmt.d1(v)} unit="°C" height={44} scrubT={scrubRow?.t ?? null} />
                </div>
            </Group>

            <Group
                index="02"
                title="Power & sun"
                gkey="power"
            >
                {/* 2×2 so the longer labels (Ambient light, Orientation) have
                  * room and don't squish — battery + solar stay on one line. */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px 16px', padding: '14px 0' }}>
                    <Metric
                        label="Battery"
                        value={batt != null ? tlmFmt.d2(batt) : '—'}
                        unit={batt != null ? 'V' : undefined}
                        icon={soc != null ? <BatteryIcon soc={soc} color={battCol} /> : undefined}
                    />
                    <Metric
                        label="Solar"
                        value={solar != null ? tlmFmt.d2(solar) : '—'}
                        unit={solar != null ? 'V' : undefined}
                        icon={solar != null ? <SolarIcon color={solar >= 1 ? '#C9922E' : 'var(--t-text-3)'} /> : undefined}
                    />
                    <Metric
                        label="Ambient light"
                        value={lux != null ? Math.round(lux).toLocaleString('en-US') : '—'}
                        unit={lux != null ? 'lux' : undefined}
                        icon={lux != null ? <DaylightIcon lux={lux} /> : undefined}
                    />
                    <Metric
                        label="Orientation"
                        value={tilt != null ? `${Math.round(tilt)}°` : '—'}
                        icon={tilt != null ? <TiltIcon deg={tilt} color={tiltCol} /> : undefined}
                    />
                </div>
            </Group>

            <Group
                index="03"
                title="Link"
                gkey="link"
            >
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0 12px', padding: '14px 0' }}>
                    <Metric label="Gateways" value={gwNow != null ? `${gwNow}` : '—'} unit={gwVisible != null ? `/ ${gwVisible}` : undefined} />
                    <Metric label="GPS sats" value={row?.sats != null ? `${row.sats}` : '—'} />
                    <Metric label="Tx Strength" value={rssi != null ? tlmFmt.int(rssi) : '—'} unit={rssi != null ? 'dBm' : undefined} />
                    <Metric label="Tx Clarity" value={snr != null ? tlmFmt.d1(snr) : '—'} unit={snr != null ? 'dB' : undefined} />
                </div>
            </Group>


            {flight.times.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px 20px', flexShrink: 0 }}>
                    <span className="mono" style={{ fontSize: 9.5, color: 'var(--t-text-4)' }}>
                        {stamp(flight.times[0])}
                    </span>
                    <span className="eyebrow" style={{ color: 'var(--t-text-4)', fontSize: 9 }}>
                        {rows.length} packets
                    </span>
                    <span className="mono" style={{ fontSize: 9.5, color: 'var(--t-text-4)' }}>
                        {stamp(flight.times[flight.times.length - 1])}
                    </span>
                </div>
            )}
            </>
            )}
        </>
    );
}
