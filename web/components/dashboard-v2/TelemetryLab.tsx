/**
 * Telemetry Lab — analytical charts + packet inspector.
 *
 * Three stacked dual-axis charts (POWER, THERMAL, RF LINK) on the left,
 * with a synchronized packet inspector on the right showing every field
 * of the selected row. All anomaly events (GPS dropouts, battery
 * transitions) are derived from real Supabase rows, not hardcoded.
 *
 * Click any row in the packet table at the bottom to inspect it.
 */
'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
    Age, Chrome, KV,
    fmt,
    DASHBOARD_V2_TABS,
    type TelemetryRow,
} from './atoms';
import { useTelemetry, type DeviceSummary } from './useTelemetry';
import { useTickingNow, useElementSize, ConnectionPill, V1Link, fmtPressure } from './shared';

type RangeKey = '1h' | '6h' | '12h' | '24h' | 'all';
const RANGE_MS: Record<RangeKey, number | null> = {
    '1h':  60 * 60 * 1000,
    '6h':  6  * 60 * 60 * 1000,
    '12h': 12 * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    'all': null,
};

interface AnomalyEvent {
    id: string;
    type: 'GPS DROPOUT' | 'BATT VOLTAGE DROP' | 'SOLAR CHARGING' | 'BATTERY LOW';
    severity: 'warn' | 'info';
    t: number;
    end: number;
    detail: string;
}

function detectEvents(rows: TelemetryRow[]): AnomalyEvent[] {
    if (!rows.length) return [];
    const out: AnomalyEvent[] = [];

    /* GPS dropouts — runs of consecutive null-position packets. */
    let dropStart: number | null = null;
    let dropCount = 0;
    rows.forEach((r) => {
        if (r.lat === null || r.lon === null) {
            if (dropStart === null) dropStart = r.t;
            dropCount += 1;
        } else if (dropStart !== null) {
            out.push({
                id: `gps-${dropStart}`,
                type: 'GPS DROPOUT',
                severity: 'warn',
                t: dropStart,
                end: r.t,
                detail: `${dropCount} packet${dropCount === 1 ? '' : 's'} without GPS fix`,
            });
            dropStart = null;
            dropCount = 0;
        }
    });
    if (dropStart !== null) {
        out.push({
            id: `gps-${dropStart}-ongoing`,
            type: 'GPS DROPOUT',
            severity: 'warn',
            t: dropStart,
            end: rows[rows.length - 1].t,
            detail: `${dropCount} packet${dropCount === 1 ? '' : 's'} (ongoing)`,
        });
    }

    /* Battery voltage drops > 0.5V between consecutive packets. */
    for (let i = 1; i < rows.length; i++) {
        const a = rows[i - 1].batt;
        const b = rows[i].batt;
        if (a !== null && b !== null && a > 4.5 && b < 4.0) {
            out.push({
                id: `batt-${rows[i].t}`,
                type: 'BATT VOLTAGE DROP',
                severity: 'info',
                t: rows[i].t,
                end: rows[i].t,
                detail: `${a.toFixed(2)}V → ${b.toFixed(2)}V`,
            });
        }
    }

    /* Solar recovery — first time solar climbs back over 4.5V. */
    for (let i = 1; i < rows.length; i++) {
        const a = rows[i - 1].sol;
        const b = rows[i].sol;
        if (a !== null && b !== null && a < 4.5 && b >= 4.5) {
            out.push({
                id: `sol-${rows[i].t}`,
                type: 'SOLAR CHARGING',
                severity: 'info',
                t: rows[i].t,
                end: rows[i].t,
                detail: 'V_sol crossed 4.5V threshold',
            });
            break;
        }
    }

    /* Battery low. */
    const latestBatt = [...rows].reverse().find(r => r.batt !== null);
    if (latestBatt && latestBatt.batt !== null && latestBatt.batt < 3.5) {
        out.push({
            id: `batlow-${latestBatt.t}`,
            type: 'BATTERY LOW',
            severity: 'warn',
            t: latestBatt.t,
            end: latestBatt.t,
            detail: `latest reading ${latestBatt.batt.toFixed(2)}V (< 3.5V)`,
        });
    }

    return out.sort((a, b) => b.t - a.t);
}

export default function TelemetryLabScreen() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialSelectedId = searchParams.get('device');
    const now = useTickingNow();

    const {
        devices, selectedId, setSelectedId,
        rows, deviceInfo, status, lastFetchedAt,
    } = useTelemetry({ initialSelectedId });

    const [range, setRange] = useState<RangeKey>('all');
    const [selectedPacketT, setSelectedPacketT] = useState<number | null>(null);

    const visibleRows = useMemo(() => {
        if (rows.length === 0) return rows;
        const ms = RANGE_MS[range];
        if (ms === null) return rows;
        const cutoff = rows[rows.length - 1].t - ms;
        return rows.filter(r => r.t >= cutoff);
    }, [rows, range]);

    /* Default selection: the latest packet in the visible window. */
    const selectedPacket: TelemetryRow | null = useMemo(() => {
        if (!visibleRows.length) return null;
        if (selectedPacketT === null) return visibleRows[visibleRows.length - 1];
        return visibleRows.find(r => r.t === selectedPacketT) ?? visibleRows[visibleRows.length - 1];
    }, [visibleRows, selectedPacketT]);

    const events = useMemo(() => detectEvents(visibleRows), [visibleRows]);

    const lastFixRow = useMemo(
        () => [...rows].reverse().find(r => r.lat !== null && r.lon !== null) ?? null,
        [rows],
    );

    const selectedDevice: DeviceSummary | null =
        selectedId ? devices.find(d => d.id === selectedId) ?? null : null;

    function handleNavigate(path: string) {
        const url = selectedId ? `${path}?device=${encodeURIComponent(selectedId)}` : path;
        router.push(url);
    }

    function handleSelectDevice(id: string) {
        setSelectedId(id);
        setSelectedPacketT(null);
        const params = new URLSearchParams(searchParams.toString());
        params.set('device', id);
        router.replace(`/dashboard-v2/lab?${params.toString()}`);
    }

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2/lab"
                onNavigate={handleNavigate}
                version={deviceInfo?.firmware ?? undefined}
                lastUplinkT={rows.length ? rows[rows.length - 1].t : null}
                lastFixT={lastFixRow?.t ?? null}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={lastFetchedAt} now={now} />
                        <span style={{ color: 'var(--sl-text-dim)', fontSize: 11 }}>analysis mode</span>
                        <span style={{ fontSize: 11 }}>
                            {selectedDevice?.callsign ?? selectedDevice?.id ?? '—'}
                        </span>
                        <V1Link />
                    </>
                }
            />

            {/* Toolbar */}
            <Toolbar
                devices={devices}
                selectedId={selectedId}
                onSelect={handleSelectDevice}
                range={range}
                onRangeChange={setRange}
                visibleCount={visibleRows.length}
                totalCount={rows.length}
            />

            <main style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 480px', minHeight: 0 }}>
                <ChartsColumn rows={visibleRows} selectedPacketT={selectedPacket?.t ?? null} onSelectPacket={setSelectedPacketT} />
                <InspectorColumn
                    rows={visibleRows}
                    selectedPacket={selectedPacket}
                    events={events}
                    onSelectPacket={setSelectedPacketT}
                    deviceInfo={deviceInfo}
                    now={now}
                />
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Toolbar
 * ────────────────────────────────────────────────────────────── */
function Toolbar({ devices, selectedId, onSelect, range, onRangeChange, visibleCount, totalCount }: {
    devices: DeviceSummary[];
    selectedId: string | null;
    onSelect: (id: string) => void;
    range: RangeKey;
    onRangeChange: (r: RangeKey) => void;
    visibleCount: number;
    totalCount: number;
}) {
    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            padding: '10px 20px',
            borderBottom: '1px solid var(--sl-border)',
            gap: 16,
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <span className="sl-label-xs">DEVICE</span>
            <select
                value={selectedId ?? ''}
                onChange={(e) => onSelect(e.target.value)}
                style={{
                    background: 'transparent',
                    border: '1px solid var(--sl-border-hi)',
                    color: 'var(--sl-text)',
                    fontFamily: 'var(--sl-mono)',
                    fontSize: 12,
                    padding: '4px 8px',
                    cursor: 'pointer',
                }}
            >
                {devices.length === 0 && <option value="">no devices</option>}
                {devices.map(d => (
                    <option key={d.id} value={d.id} style={{ background: 'var(--sl-bg-2)' }}>
                        {d.callsign ?? d.id}
                    </option>
                ))}
            </select>

            <div style={{ width: 1, height: 18, background: 'var(--sl-border)' }} />

            <span className="sl-label-xs">RANGE</span>
            <div style={{ display: 'flex', gap: 4 }}>
                {(['1h', '6h', '12h', '24h', 'all'] as RangeKey[]).map(r => (
                    <button
                        key={r}
                        type="button"
                        onClick={() => onRangeChange(r)}
                        className={'sl-pill ' + (r === range ? 'teal' : 'dim')}
                        style={{ cursor: 'pointer', background: 'none' }}
                    >
                        {r.toUpperCase()}
                    </button>
                ))}
            </div>

            <div style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                {visibleCount.toLocaleString()} of {totalCount.toLocaleString()} packets in window
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Charts column
 * ────────────────────────────────────────────────────────────── */
function ChartsColumn({ rows, selectedPacketT, onSelectPacket }: {
    rows: TelemetryRow[];
    selectedPacketT: number | null;
    onSelectPacket: (t: number) => void;
}) {
    return (
        <div style={{
            borderRight: '1px solid var(--sl-border)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            minHeight: 0,
        }}>
            <ChartBlock title="POWER SYSTEM" subtitle="battery, solar, charging cycle"
                legend={[
                    { color: 'var(--sl-ok-mute)',  label: 'V_BAT (V)' },
                    { color: 'var(--sl-neutral)',  label: 'V_SOL (V)' },
                    { color: 'var(--sl-text-dim2)', label: '▒ NIGHT (lux < 1000)' },
                ]}
                rows={rows}
                seriesA={{ getY: r => r.batt, color: 'var(--sl-ok-mute)', label: 'V_BAT', min: 3.0, max: 5.5 }}
                seriesB={{ getY: r => r.sol,  color: 'var(--sl-neutral)', label: 'V_SOL', min: 0,   max: 6 }}
                shade={rows.map(r => r.lux)}
                selectedPacketT={selectedPacketT}
                onSelectPacket={onSelectPacket}
                height={180}
            />
            <ChartBlock title="THERMAL" subtitle="core temperature, raw barometer counts"
                legend={[
                    { color: 'var(--sl-alert)',   label: 'TEMP (°C)' },
                    { color: 'var(--sl-neutral)', label: 'PRES_RAW (dn)' },
                ]}
                rows={rows}
                seriesA={{ getY: r => r.temp, color: 'var(--sl-alert)', label: 'TEMP' }}
                seriesB={{ getY: r => r.pres, color: 'var(--sl-neutral)', label: 'PRES', opacity: 0.6 }}
                selectedPacketT={selectedPacketT}
                onSelectPacket={onSelectPacket}
                height={140}
            />
            <ChartBlock title="RF LINK" subtitle="signal vs noise · GPS lock state"
                legend={[
                    { color: 'var(--sl-ok-mute)', label: 'RSSI (dBm)' },
                    { color: 'var(--sl-neutral)', label: 'SNR (dB)' },
                    { color: 'var(--sl-alert)',   label: '▒ GPS DROPOUT' },
                ]}
                rows={rows}
                seriesA={{ getY: r => r.rssi, color: 'var(--sl-ok-mute)', label: 'RSSI' }}
                seriesB={{ getY: r => r.snr,  color: 'var(--sl-neutral)', label: 'SNR' }}
                dropoutMask={rows.map(r => r.lat === null || r.lon === null)}
                selectedPacketT={selectedPacketT}
                onSelectPacket={onSelectPacket}
                height={148}
                flex
            />
        </div>
    );
}

interface SeriesSpec {
    getY: (r: TelemetryRow) => number | null;
    color: string;
    label: string;
    min?: number;
    max?: number;
    opacity?: number;
}

function ChartBlock({ title, subtitle, legend, rows, seriesA, seriesB, shade, dropoutMask, selectedPacketT, onSelectPacket, height, flex }: {
    title: string;
    subtitle: string;
    legend: Array<{ color: string; label: string }>;
    rows: TelemetryRow[];
    seriesA: SeriesSpec;
    seriesB: SeriesSpec;
    shade?: Array<number | null>;
    dropoutMask?: boolean[];
    selectedPacketT: number | null;
    onSelectPacket: (t: number) => void;
    height: number;
    flex?: boolean;
}) {
    const { ref, width } = useElementSize(800, height);
    return (
        <div style={{
            padding: 14,
            borderBottom: '1px solid var(--sl-border)',
            ...(flex ? { flex: 1, minHeight: 0 } : {}),
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <span className="sl-label-xs" style={{ color: 'var(--sl-text)' }}>{title}</span>
                <span style={{ fontSize: 10, color: 'var(--sl-text-dim2)' }}>{subtitle}</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, fontSize: 10 }}>
                    {legend.map((l, i) => (
                        <span key={i} style={{ color: l.color }}>● {l.label}</span>
                    ))}
                </div>
            </div>
            <div ref={ref} style={{ width: '100%' }}>
                {rows.length >= 2 ? (
                    <DualChart
                        data={rows}
                        width={width}
                        height={height}
                        seriesA={seriesA}
                        seriesB={seriesB}
                        shade={shade}
                        dropoutMask={dropoutMask}
                        scrubT={selectedPacketT}
                        onPick={onSelectPacket}
                    />
                ) : (
                    <div style={{
                        height,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'var(--sl-text-dim2)',
                        fontSize: 11,
                        letterSpacing: '0.10em',
                        textTransform: 'uppercase',
                    }}>
                        Awaiting packets…
                    </div>
                )}
            </div>
        </div>
    );
}

function DualChart({ data, width, height, seriesA, seriesB, shade, dropoutMask, scrubT, onPick }: {
    data: TelemetryRow[];
    width: number;
    height: number;
    seriesA: SeriesSpec;
    seriesB: SeriesSpec;
    shade?: Array<number | null>;
    dropoutMask?: boolean[];
    scrubT: number | null;
    onPick: (t: number) => void;
}) {
    const padL = 44, padR = 44, padT = 8, padB = 22;
    const innerW = Math.max(1, width - padL - padR);
    const innerH = Math.max(1, height - padT - padB);
    const t0 = data[0].t;
    const t1 = data[data.length - 1].t;
    const tspan = Math.max(1, t1 - t0);

    const validA = data.map(r => seriesA.getY(r)).filter((v): v is number => v !== null && Number.isFinite(v));
    const validB = data.map(r => seriesB.getY(r)).filter((v): v is number => v !== null && Number.isFinite(v));
    const aLo = seriesA.min !== undefined ? seriesA.min : (validA.length ? Math.min(...validA) : 0);
    const aHi = seriesA.max !== undefined ? seriesA.max : (validA.length ? Math.max(...validA) : 1);
    const bLo = seriesB.min !== undefined ? seriesB.min : (validB.length ? Math.min(...validB) : 0);
    const bHi = seriesB.max !== undefined ? seriesB.max : (validB.length ? Math.max(...validB) : 1);
    const aR = aHi - aLo || 1;
    const bR = bHi - bLo || 1;

    const xOf = (t: number) => padL + ((t - t0) / tspan) * innerW;
    const yA = (v: number) => padT + innerH - ((v - aLo) / aR) * innerH;
    const yB = (v: number) => padT + innerH - ((v - bLo) / bR) * innerH;

    const buildPath = (getY: (r: TelemetryRow) => number | null, yOf: (v: number) => number) => {
        let d = ''; let started = false;
        data.forEach(r => {
            const v = getY(r);
            if (v === null || v === undefined || !Number.isFinite(v)) { started = false; return; }
            d += (started ? ' L' : 'M') + xOf(r.t).toFixed(1) + ' ' + yOf(v).toFixed(1);
            started = true;
        });
        return d;
    };
    const aPath = buildPath(seriesA.getY, yA);
    const bPath = buildPath(seriesB.getY, yB);

    /* Compute shade and dropout bands. */
    const shadeBands: Array<[number, number]> = [];
    if (shade) {
        let bs: number | null = null;
        for (let i = 0; i < data.length; i++) {
            const lo = (shade[i] ?? Infinity) < 1000;
            if (lo && bs === null) bs = data[i].t;
            else if (!lo && bs !== null) { shadeBands.push([bs, data[i].t]); bs = null; }
        }
        if (bs !== null) shadeBands.push([bs, data[data.length - 1].t]);
    }
    const dropoutBands: Array<[number, number]> = [];
    if (dropoutMask) {
        let bs: number | null = null;
        for (let i = 0; i < data.length; i++) {
            if (dropoutMask[i] && bs === null) bs = data[i].t;
            else if (!dropoutMask[i] && bs !== null) { dropoutBands.push([bs, data[i].t]); bs = null; }
        }
        if (bs !== null) dropoutBands.push([bs, data[data.length - 1].t]);
    }

    function handleClick(e: React.MouseEvent<SVGSVGElement>) {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left - padL;
        const f = Math.max(0, Math.min(1, x / innerW));
        const t = t0 + tspan * f;
        let best = data[0];
        for (const r of data) {
            if (Math.abs(r.t - t) < Math.abs(best.t - t)) best = r;
        }
        onPick(best.t);
    }

    return (
        <svg
            width={width}
            height={height}
            onClick={handleClick}
            style={{ display: 'block', overflow: 'visible', cursor: 'crosshair' }}
        >
            {shadeBands.map(([a, b], i) => (
                <rect key={'s' + i} x={xOf(a)} y={padT} width={Math.max(0, xOf(b) - xOf(a))} height={innerH}
                    fill="var(--sl-neutral)" opacity="0.05" />
            ))}
            {dropoutBands.map(([a, b], i) => (
                <rect key={'d' + i} x={xOf(a)} y={padT} width={Math.max(0, xOf(b) - xOf(a))} height={innerH}
                    fill="var(--sl-alert)" opacity="0.10" />
            ))}
            {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
                const y = padT + innerH * (1 - f);
                return (
                    <g key={i}>
                        <line x1={padL} y1={y} x2={padL + innerW} y2={y} stroke="var(--sl-grid)" />
                        <text x={padL - 6} y={y + 3} textAnchor="end" className="sl-tick" fill={seriesA.color}>
                            {(aLo + aR * f).toFixed(aR < 10 ? 2 : 0)}
                        </text>
                        <text x={padL + innerW + 6} y={y + 3} textAnchor="start" className="sl-tick" fill={seriesB.color}>
                            {(bLo + bR * f).toFixed(bR < 10 ? 2 : 0)}
                        </text>
                    </g>
                );
            })}
            {[0, 0.2, 0.4, 0.6, 0.8, 1].map((f, i) => {
                const x = padL + innerW * f;
                const t = t0 + tspan * f;
                return (
                    <g key={i}>
                        <line x1={x} y1={padT} x2={x} y2={padT + innerH} stroke="var(--sl-grid)" strokeDasharray="2 4" />
                        <text x={x} y={padT + innerH + 14} textAnchor="middle" className="sl-tick">{fmt.time(t)}</text>
                    </g>
                );
            })}
            <path d={aPath} fill="none" stroke={seriesA.color} strokeWidth="1.5" />
            <path d={bPath} fill="none" stroke={seriesB.color} strokeWidth="1.4" opacity={seriesB.opacity ?? 1} />
            {scrubT !== null && scrubT >= t0 && scrubT <= t1 && (
                <line
                    x1={xOf(scrubT)} y1={padT}
                    x2={xOf(scrubT)} y2={padT + innerH}
                    stroke="var(--sl-ok)"
                    strokeWidth="1.5"
                    strokeDasharray="3 2"
                />
            )}
        </svg>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Inspector column — selected packet detail + events + table
 * ────────────────────────────────────────────────────────────── */
function InspectorColumn({ rows, selectedPacket, events, onSelectPacket, deviceInfo, now }: {
    rows: TelemetryRow[];
    selectedPacket: TelemetryRow | null;
    events: AnomalyEvent[];
    onSelectPacket: (t: number) => void;
    deviceInfo: { firmware: string | null; freq_mhz: number | null; sf: string | null; packet_count: number } | null;
    now: number;
}) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
            <PacketHeader selectedPacket={selectedPacket} totalRows={rows.length} now={now} />
            <div style={{ flex: 1, overflow: 'auto', padding: '0 16px' }}>
                {selectedPacket ? (
                    <>
                        <PacketDetail packet={selectedPacket} deviceInfo={deviceInfo} />
                        <Section title={`EVENTS · ${events.length}`}>
                            {events.length === 0 ? (
                                <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)', padding: '6px 0' }}>
                                    No anomalies detected in the visible window.
                                </div>
                            ) : (
                                events.map(e => (
                                    <button
                                        key={e.id}
                                        type="button"
                                        onClick={() => onSelectPacket(e.t)}
                                        style={{
                                            display: 'block',
                                            width: '100%',
                                            padding: '6px 0',
                                            fontSize: 11,
                                            borderBottom: '1px dashed var(--sl-border)',
                                            background: 'transparent',
                                            textAlign: 'left',
                                            color: 'inherit',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ color: e.severity === 'warn' ? 'var(--sl-alert)' : 'var(--sl-ok)', letterSpacing: '0.06em' }}>
                                                {e.type}
                                            </span>
                                            <span style={{ color: 'var(--sl-text-dim3)' }}>
                                                {e.end > e.t ? fmt.duration(e.end - e.t) : fmt.time(e.t)}
                                            </span>
                                        </div>
                                        <div style={{ color: 'var(--sl-text-dim2)', fontSize: 10 }}>
                                            {e.detail} · {fmt.time(e.t)}{e.end > e.t ? ` → ${fmt.time(e.end)}` : ''}
                                        </div>
                                    </button>
                                ))
                            )}
                        </Section>
                        <Section title={`PACKET LOG · ${rows.length}`}>
                            <PacketTable rows={rows} selectedT={selectedPacket.t} onSelect={onSelectPacket} />
                        </Section>
                    </>
                ) : (
                    <div style={{ padding: 16, fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                        No packets in the selected window.
                    </div>
                )}
            </div>
        </div>
    );
}

function PacketHeader({ selectedPacket, totalRows, now }: {
    selectedPacket: TelemetryRow | null;
    totalRows: number;
    now: number;
}) {
    if (!selectedPacket) {
        return (
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--sl-border)' }}>
                <span className="sl-label-xs">SELECTED PACKET</span>
            </div>
        );
    }
    const idx = selectedPacket ? totalRows : null;
    const noFix = selectedPacket.lat === null || selectedPacket.lon === null;
    return (
        <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--sl-border)' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
                <span className="sl-label-xs">SELECTED PACKET</span>
                <span style={{ fontSize: 10, color: 'var(--sl-text-dim3)' }}>
                    {idx !== null ? `${idx} packets in window` : ''}
                </span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--sl-ok)', fontFamily: 'var(--sl-mono)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 10 }}>
                {fmt.datetime(selectedPacket.t)} UTC
                <Age t={selectedPacket.t} now={now} dot />
            </div>
            {noFix && (
                <div style={{
                    marginTop: 10,
                    padding: '8px 10px',
                    background: 'var(--sl-alert-soft)',
                    border: '1px solid rgba(245,185,66,0.3)',
                    fontSize: 10,
                    color: 'var(--sl-alert)',
                    letterSpacing: '0.10em',
                    textTransform: 'uppercase',
                    fontWeight: 500,
                }}>
                    NO GPS FIX · POSITION DATA STALE
                </div>
            )}
        </div>
    );
}

function PacketDetail({ packet, deviceInfo }: {
    packet: TelemetryRow;
    deviceInfo: { firmware: string | null; freq_mhz: number | null; sf: string | null; packet_count: number } | null;
}) {
    const accel = packet.ax !== null && packet.ay !== null && packet.az !== null
        ? Math.sqrt(packet.ax ** 2 + packet.ay ** 2 + packet.az ** 2)
        : null;
    return (
        <>
            <Section title="POSITION">
                <KV k="lat" v={fmt.lat(packet.lat)} accent={packet.lat !== null ? 'teal' : 'dim'} />
                <KV k="lon" v={fmt.lon(packet.lon)} accent={packet.lon !== null ? 'teal' : 'dim'} />
                <KV k="alt_m"  v={fmt.num(packet.alt, 0)} u={packet.alt !== null ? 'm' : undefined} />
                <KV k="alt_ft" v={packet.alt !== null ? (packet.alt * 3.281).toFixed(0) : '—'} u={packet.alt !== null ? 'ft' : undefined} />
                <KV k="gps_sats"    v={fmt.num(packet.sats, 0)} />
                <KV k="gps_speed"   v={fmt.num(packet.spd, 2)} u={packet.spd !== null ? 'm/s' : undefined} />
                <KV k="gps_heading" v={fmt.num(packet.hdg, 1)} u={packet.hdg !== null ? '°' : undefined} />
                <KV k="hdop"        v={fmt.num(packet.hdop, 2)} />
            </Section>
            <Section title="POWER">
                <KV k="v_bat"   v={fmt.num(packet.batt, 3)} u={packet.batt !== null ? 'V' : undefined} accent={packet.batt !== null && packet.batt < 3.5 ? 'amber' : 'teal'} />
                <KV k="v_sol"   v={fmt.num(packet.sol, 3)}  u={packet.sol  !== null ? 'V' : undefined} />
                <KV k="charging" v={packet.batt !== null && packet.sol !== null ? (packet.sol > packet.batt ? 'YES' : 'NO') : '—'}
                    accent={packet.batt !== null && packet.sol !== null && packet.sol > packet.batt ? 'teal' : 'dim'} />
                <KV k="power_mode" v={packet.power_mode ?? '—'} />
                <KV k="sleep_ms"   v={fmt.num(packet.sleep_ms, 0)} />
                <KV k="uptime"     v={packet.uptime_s !== null ? fmt.duration(packet.uptime_s * 1000) : '—'} />
            </Section>
            <Section title="ENVIRONMENT">
                <KV k="temp"       v={fmt.num(packet.temp, 2)} u={packet.temp !== null ? '°C' : undefined} />
                <KV k="pres_raw"   v={fmtPressure(packet.pres)} />
                <KV k="ambient_lux" v={fmt.num(packet.lux, 0)} u={packet.lux !== null ? 'lx' : undefined} />
                <KV k="uv_index"    v={fmt.num(packet.uv, 1)} />
            </Section>
            <Section title="RF LINK">
                <KV k="rssi" v={fmt.num(packet.rssi, 0)} u={packet.rssi !== null ? 'dBm' : undefined} />
                <KV k="snr"  v={fmt.num(packet.snr, 2)}  u={packet.snr !== null ? 'dB' : undefined} />
                <KV k="freq" v={packet.frequency_hz !== null ? (packet.frequency_hz / 1_000_000).toFixed(1) : (deviceInfo?.freq_mhz?.toFixed(1) ?? '—')}
                    u={(packet.frequency_hz !== null || deviceInfo?.freq_mhz) ? 'MHz' : undefined} />
                <KV k="sf"   v={packet.lora_sf !== null ? `SF${packet.lora_sf}` : (deviceInfo?.sf ?? '—')} />
                <KV k="bw"   v={packet.lora_bw !== null ? `${(packet.lora_bw / 1000).toFixed(0)} kHz` : '—'} />
                <KV k="tx_count" v={packet.tx_count !== null ? packet.tx_count.toLocaleString() : '—'} />
            </Section>
            <Section title="IMU">
                <KV k="accel_x" v={fmt.num(packet.ax, 2)} u={packet.ax !== null ? 'm/s²' : undefined} />
                <KV k="accel_y" v={fmt.num(packet.ay, 2)} u={packet.ay !== null ? 'm/s²' : undefined} />
                <KV k="accel_z" v={fmt.num(packet.az, 2)} u={packet.az !== null ? 'm/s²' : undefined} />
                <KV k="|a|"     v={accel !== null ? accel.toFixed(2) : '—'} u={accel !== null ? 'm/s²' : undefined} />
                <KV k="vel_x"   v={fmt.num(packet.vx, 3)} u={packet.vx !== null ? 'm/s' : undefined} />
                <KV k="vel_y"   v={fmt.num(packet.vy, 3)} u={packet.vy !== null ? 'm/s' : undefined} />
            </Section>
        </>
    );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div style={{ padding: '14px 0', borderBottom: '1px solid var(--sl-border)' }}>
            <div className="sl-label-xs" style={{ marginBottom: 8 }}>{title}</div>
            {children}
        </div>
    );
}

function PacketTable({ rows, selectedT, onSelect }: {
    rows: TelemetryRow[];
    selectedT: number;
    onSelect: (t: number) => void;
}) {
    /* Show newest first, cap at 200 to keep the DOM happy. */
    const list = [...rows].reverse().slice(0, 200);
    return (
        <div style={{ fontSize: 10, fontFamily: 'var(--sl-mono)' }}>
            <div style={{
                display: 'grid',
                gridTemplateColumns: '70px 60px 50px 50px 40px',
                gap: 6,
                padding: '4px 0',
                color: 'var(--sl-text-dim3)',
                borderBottom: '1px solid var(--sl-border)',
                position: 'sticky',
                top: 0,
                background: 'var(--sl-bg)',
            }}>
                <span>TIME</span>
                <span style={{ textAlign: 'right' }}>ALT</span>
                <span style={{ textAlign: 'right' }}>BATT</span>
                <span style={{ textAlign: 'right' }}>RSSI</span>
                <span style={{ textAlign: 'right' }}>SAT</span>
            </div>
            {list.map(r => {
                const isSel = r.t === selectedT;
                const noFix = r.lat === null;
                return (
                    <button
                        key={r.t}
                        type="button"
                        onClick={() => onSelect(r.t)}
                        style={{
                            display: 'grid',
                            gridTemplateColumns: '70px 60px 50px 50px 40px',
                            gap: 6,
                            padding: '3px 0',
                            border: 'none',
                            borderBottom: '1px solid var(--sl-divider)',
                            background: isSel ? 'var(--sl-ok-soft)' : 'transparent',
                            color: isSel ? 'var(--sl-text-hi)' : (noFix ? 'var(--sl-alert)' : 'var(--sl-text)'),
                            cursor: 'pointer',
                            font: 'inherit',
                            width: '100%',
                            textAlign: 'left',
                        }}
                    >
                        <span>{fmt.time(r.t)}</span>
                        <span style={{ textAlign: 'right' }}>{r.alt !== null ? r.alt.toFixed(0) : '—'}</span>
                        <span style={{ textAlign: 'right' }}>{r.batt !== null ? r.batt.toFixed(2) : '—'}</span>
                        <span style={{ textAlign: 'right' }}>{r.rssi !== null ? r.rssi.toString() : '—'}</span>
                        <span style={{ textAlign: 'right' }}>{r.sats !== null ? r.sats.toString() : '—'}</span>
                    </button>
                );
            })}
        </div>
    );
}

