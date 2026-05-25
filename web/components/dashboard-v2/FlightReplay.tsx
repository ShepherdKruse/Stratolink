/**
 * Flight Replay — comprehensive read-only view of a single completed flight.
 *
 * Shares the dashboard-v2 dark theme and atoms with Mission Control / Device
 * Tracker. Layout: identity header → mission KPI strip → 3-column body
 * (map · synchronized chart stack · packet inspector) → global scrubber that
 * drives every column.
 *
 * Fed by useFlightReplay(): a full mission-window Supabase fetch for real
 * flights, or curated sample data. Every value is real or '—'.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
    Age, Chart, Chrome, KPI, KV,
    fmt,
    DASHBOARD_V2_TABS,
    type TelemetryRow,
} from './atoms';
import { useTickingNow, useElementSize, V1Link, fmtPressure, fmtAltitudeM } from './shared';
import V2MissionMap, { type V2Balloon, type V2FlightPoint } from './V2MissionMap';
import GatewayRangeControls from './GatewayRangeControls';
import {
    useFlightReplay,
    haversineKm,
    type FlightReplayMeta,
} from '@/lib/flights/pastFlights';

type RangeKey = '1h' | '6h' | '24h' | 'all';
const RANGE_MS: Record<RangeKey, number | null> = {
    '1h': 60 * 60 * 1000,
    '6h': 6 * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    all: null,
};

interface MissionStats {
    peakAltM: number | null;
    minTempC: number | null;
    maxSpeed: number | null;
    distanceKm: number;
    fixCount: number;
    rowCount: number;
}

interface ReplayEvent {
    id: string;
    type: string;
    severity: 'warn' | 'info';
    t: number;
    end: number;
    detail: string;
}

/* GPS dropouts + power transitions, all derived from the real rows. */
function detectEvents(rows: TelemetryRow[]): ReplayEvent[] {
    if (!rows.length) return [];
    const out: ReplayEvent[] = [];

    let dropStart: number | null = null;
    let dropCount = 0;
    rows.forEach((r) => {
        if (r.lat === null || r.lon === null) {
            if (dropStart === null) dropStart = r.t;
            dropCount += 1;
        } else if (dropStart !== null) {
            if (dropCount >= 3) {
                out.push({
                    id: `gps-${dropStart}`,
                    type: 'GPS DROPOUT',
                    severity: 'warn',
                    t: dropStart,
                    end: r.t,
                    detail: `${dropCount} packet${dropCount === 1 ? '' : 's'} without a fix`,
                });
            }
            dropStart = null;
            dropCount = 0;
        }
    });
    if (dropStart !== null && dropCount >= 3) {
        out.push({
            id: `gps-${dropStart}-end`,
            type: 'GPS DROPOUT',
            severity: 'warn',
            t: dropStart,
            end: rows[rows.length - 1].t,
            detail: `${dropCount} packets without a fix (to end of flight)`,
        });
    }

    for (let i = 1; i < rows.length; i++) {
        const a = rows[i - 1].batt;
        const b = rows[i].batt;
        if (a !== null && b !== null && a - b > 1.0) {
            out.push({
                id: `batt-${rows[i].t}`,
                type: 'VOLTAGE DROP',
                severity: 'info',
                t: rows[i].t,
                end: rows[i].t,
                detail: `${a.toFixed(2)}V → ${b.toFixed(2)}V`,
            });
        }
    }

    const minTemp = rows.reduce<TelemetryRow | null>(
        (acc, r) => (r.temp !== null && (acc === null || (acc.temp as number) > r.temp) ? r : acc),
        null,
    );
    if (minTemp && minTemp.temp !== null) {
        out.push({
            id: `cold-${minTemp.t}`,
            type: 'COLDEST POINT',
            severity: 'info',
            t: minTemp.t,
            end: minTemp.t,
            detail: `${minTemp.temp.toFixed(1)}°C`,
        });
    }

    return out.sort((a, b) => a.t - b.t);
}

export default function FlightReplayScreen({ flightId }: { flightId: string }) {
    const router = useRouter();
    const now = useTickingNow();
    const { rows, meta, status, loading, notFound } = useFlightReplay(flightId);

    const [range, setRange] = useState<RangeKey>('all');
    const [scrubT, setScrubT] = useState<number | null>(null);

    const visibleRows = useMemo(() => {
        if (rows.length === 0) return rows;
        const ms = RANGE_MS[range];
        if (ms === null) return rows;
        const cutoff = rows[rows.length - 1].t - ms;
        return rows.filter((r) => r.t >= cutoff);
    }, [rows, range]);

    /* Default the scrubber to the end of the visible window. */
    const effectiveScrubT: number | null = useMemo(() => {
        if (!visibleRows.length) return null;
        const t0 = visibleRows[0].t;
        const t1 = visibleRows[visibleRows.length - 1].t;
        if (scrubT === null) return t1;
        return Math.min(Math.max(scrubT, t0), t1);
    }, [visibleRows, scrubT]);

    const scrubRow: TelemetryRow | null = useMemo(() => {
        if (!visibleRows.length || effectiveScrubT === null) return null;
        let row = visibleRows[0];
        for (const r of visibleRows) {
            if (r.t <= effectiveScrubT) row = r;
            else break;
        }
        return row;
    }, [visibleRows, effectiveScrubT]);

    const stats: MissionStats = useMemo(() => {
        const fixes = visibleRows.filter((r) => r.lat !== null && r.lon !== null) as Array<
            TelemetryRow & { lat: number; lon: number }
        >;
        let distanceKm = 0;
        for (let i = 1; i < fixes.length; i++) {
            distanceKm += haversineKm(fixes[i - 1].lat, fixes[i - 1].lon, fixes[i].lat, fixes[i].lon);
        }
        const alts = visibleRows.map((r) => r.alt).filter((v): v is number => v !== null && Number.isFinite(v));
        const temps = visibleRows.map((r) => r.temp).filter((v): v is number => v !== null && Number.isFinite(v));
        const speeds = visibleRows.map((r) => r.spd).filter((v): v is number => v !== null && Number.isFinite(v));
        return {
            peakAltM: alts.length ? Math.max(...alts) : null,
            minTempC: temps.length ? Math.min(...temps) : null,
            maxSpeed: speeds.length ? Math.max(...speeds) : null,
            distanceKm,
            fixCount: fixes.length,
            rowCount: visibleRows.length,
        };
    }, [visibleRows]);

    const events = useMemo(() => detectEvents(rows), [rows]);

    const tStart = visibleRows.length ? visibleRows[0].t : null;
    const tEnd = visibleRows.length ? visibleRows[visibleRows.length - 1].t : null;
    const name = meta?.callsign ?? meta?.title ?? meta?.deviceId ?? flightId;

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2/archive"
                onNavigate={(path) => router.push(path)}
                version={meta?.firmware ?? undefined}
                lastUplinkT={tEnd}
                lastFixT={tEnd}
                now={now}
                right={
                    <>
                        <Link
                            href="/dashboard-v2/archive"
                            style={{
                                fontSize: 10,
                                letterSpacing: '0.10em',
                                textTransform: 'uppercase',
                                color: 'var(--sl-text-dim)',
                                textDecoration: 'none',
                                border: '1px solid var(--sl-border-hi)',
                                padding: '4px 8px',
                            }}
                        >
                            ← archive
                        </Link>
                        <span style={{ fontSize: 11 }}>{name}</span>
                        <V1Link />
                    </>
                }
            />

            {loading ? (
                <CenterMsg text="Loading flight…" />
            ) : notFound || !meta ? (
                <CenterMsg text="Flight not found in the archive." accent />
            ) : (
                <>
                    <IdentityStrip meta={meta} rowCount={rows.length} />
                    <MissionKpiStrip meta={meta} stats={stats} />

                    <main
                        style={{
                            flex: 1,
                            display: 'grid',
                            gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr) 320px',
                            minHeight: 0,
                            minWidth: 0,
                            background: 'var(--sl-border)',
                            gap: 1,
                        }}
                    >
                        <MapColumn rows={visibleRows} scrubRow={scrubRow} deviceId={meta.deviceId} now={now} />
                        <ChartColumn rows={visibleRows} scrubT={effectiveScrubT} scrubRow={scrubRow} />
                        <InspectorColumn scrubRow={scrubRow} events={events} onSelect={setScrubT} meta={meta} />
                    </main>

                    {tStart !== null && tEnd !== null && (
                        <Scrubber
                            rows={rows}
                            visibleRows={visibleRows}
                            tStart={tStart}
                            tEnd={tEnd}
                            scrubT={effectiveScrubT}
                            onScrub={setScrubT}
                            onReset={() => setScrubT(null)}
                            range={range}
                            onRangeChange={setRange}
                        />
                    )}
                </>
            )}
        </div>
    );
}

function CenterMsg({ text, accent }: { text: string; accent?: boolean }) {
    return (
        <div
            style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: accent ? 'var(--sl-alert)' : 'var(--sl-text-dim2)',
                fontSize: 12,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
            }}
        >
            {text}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Identity strip
 * ────────────────────────────────────────────────────────────── */
function IdentityStrip({ meta, rowCount }: { meta: FlightReplayMeta; rowCount: number }) {
    const name = meta.callsign ?? meta.title ?? meta.deviceId;
    return (
        <div
            style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 16,
                padding: '14px 24px',
                borderBottom: '1px solid var(--sl-border)',
                background: 'var(--sl-bg-1)',
                flexShrink: 0,
                flexWrap: 'wrap',
            }}
        >
            <span style={{ fontSize: 18, fontWeight: 500, color: 'var(--sl-ok)', fontFamily: 'var(--sl-mono)' }}>
                {name}
            </span>
            {meta.subtitle && (
                <span style={{ fontSize: 12, color: 'var(--sl-text-dim)', maxWidth: 520 }}>{meta.subtitle}</span>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, alignItems: 'baseline', fontSize: 11, color: 'var(--sl-text-dim)' }}>
                <span className="sl-pill dim">{meta.status?.toUpperCase() ?? '—'}</span>
                {meta.source === 'curated' && <span className="sl-pill dim">SAMPLE</span>}
                <MetaItem k="device" v={meta.deviceId} mono />
                <MetaItem k="launched" v={meta.launchedAtMs !== null ? `${fmt.datetime(meta.launchedAtMs)} UTC` : '—'} mono />
                <MetaItem k="ended" v={meta.endedAtMs !== null ? `${fmt.datetime(meta.endedAtMs)} UTC` : '—'} mono />
                {meta.comms && <MetaItem k="comms" v={meta.comms} />}
                <MetaItem k="packets" v={rowCount.toLocaleString()} mono />
            </div>
        </div>
    );
}

function MetaItem({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
    return (
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'baseline' }}>
            <span style={{ fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--sl-text-dim3)' }}>
                {k}
            </span>
            <span style={{ color: 'var(--sl-text)', fontFamily: mono ? 'var(--sl-mono)' : 'var(--sl-sans)' }}>{v}</span>
        </span>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Mission KPI strip
 * ────────────────────────────────────────────────────────────── */
function MissionKpiStrip({ meta, stats }: { meta: FlightReplayMeta; stats: MissionStats }) {
    const durationMs =
        meta.launchedAtMs !== null && meta.endedAtMs !== null ? meta.endedAtMs - meta.launchedAtMs : null;
    const altFt = stats.peakAltM !== null ? Math.round(stats.peakAltM * 3.281) : null;
    return (
        <div
            style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(6, 1fr)',
                borderBottom: '1px solid var(--sl-border)',
                background: 'var(--sl-bg-1)',
                flexShrink: 0,
            }}
        >
            <KpiCell>
                <KPI
                    label="PEAK ALTITUDE"
                    value={stats.peakAltM !== null ? stats.peakAltM.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
                    unit={stats.peakAltM !== null ? 'm' : undefined}
                    sub={altFt !== null ? `${altFt.toLocaleString()} ft` : undefined}
                    accent="ok"
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="DISTANCE"
                    value={Math.round(stats.distanceKm).toLocaleString()}
                    unit="km"
                    sub="across the track"
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="DURATION"
                    value={durationMs !== null ? fmt.duration(durationMs) : '—'}
                    sub="launch → last contact"
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="MIN TEMP"
                    value={stats.minTempC !== null ? stats.minTempC.toFixed(1) : '—'}
                    unit={stats.minTempC !== null ? '°C' : undefined}
                    sub="coldest reading"
                    accent={stats.minTempC !== null && stats.minTempC < -20 ? 'alert' : undefined}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="MAX SPEED"
                    value={stats.maxSpeed !== null ? stats.maxSpeed.toFixed(1) : '—'}
                    unit={stats.maxSpeed !== null ? 'm/s' : undefined}
                    sub="ground speed"
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="PACKETS / FIXES"
                    value={stats.rowCount.toLocaleString()}
                    sub={`${stats.fixCount.toLocaleString()} GPS fixes`}
                />
            </KpiCell>
        </div>
    );
}

function KpiCell({ children }: { children: React.ReactNode }) {
    return <div style={{ background: 'var(--sl-bg-1)', borderRight: '1px solid var(--sl-border)' }}>{children}</div>;
}

/* ──────────────────────────────────────────────────────────────
 * Map column — full track + balloon at scrub time
 * ────────────────────────────────────────────────────────────── */
function MapColumn({
    rows,
    scrubRow,
    deviceId,
    now,
}: {
    rows: TelemetryRow[];
    scrubRow: TelemetryRow | null;
    deviceId: string;
    now: number;
}) {
    const trackPoints: V2FlightPoint[] = useMemo(
        () =>
            rows
                .filter((r) => r.lat !== null && r.lon !== null)
                .map((r) => ({ lat: r.lat as number, lon: r.lon as number, t: r.t })),
        [rows],
    );

    const balloon: V2Balloon | null = useMemo(() => {
        if (scrubRow && scrubRow.lat !== null && scrubRow.lon !== null) {
            return { id: deviceId, lat: scrubRow.lat, lon: scrubRow.lon, altitude_m: scrubRow.alt };
        }
        const last = trackPoints[trackPoints.length - 1];
        return last ? { id: deviceId, lat: last.lat, lon: last.lon, altitude_m: scrubRow?.alt ?? null } : null;
    }, [scrubRow, trackPoints, deviceId]);

    /* Balloon-centered gateway range view — scrub along the flight to explain
     * past silences ("nearest gateway was 600 km away, expect silence"). */
    const [rangeMode, setRangeMode] = useState(false);
    const rangeCenter = balloon ? { lat: balloon.lat, lon: balloon.lon, altM: balloon.altitude_m } : null;

    return (
        <div style={{ position: 'relative', background: 'var(--sl-bg)', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
            <V2MissionMap
                balloons={balloon ? [balloon] : []}
                activeId={deviceId}
                flightPath={trackPoints}
                playbackT={scrubRow?.t ?? null}
                projection="globe"
                rangeCenter={rangeMode ? rangeCenter : null}
            />
            <div style={{ position: 'absolute', top: 14, left: 14, display: 'flex', gap: 6, zIndex: 1, flexWrap: 'wrap' }}>
                <span className="sl-pill dim">MAPBOX · DARK</span>
                {scrubRow?.lat !== null && scrubRow?.lat !== undefined && (
                    <span className="sl-pill dim">
                        {(scrubRow.lat as number).toFixed(2)}° · {(scrubRow.lon as number).toFixed(2)}°
                    </span>
                )}
                <span className="sl-pill dim">
                    <Age t={scrubRow?.t ?? null} now={now} compact dot prefix="scrub" />
                </span>
            </div>

            {rangeCenter && (
                <GatewayRangeControls
                    lat={rangeCenter.lat}
                    lon={rangeCenter.lon}
                    altM={rangeCenter.altM}
                    rangeMode={rangeMode}
                    onToggle={() => setRangeMode((v) => !v)}
                />
            )}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chart column — synchronized stack
 * ────────────────────────────────────────────────────────────── */
function ChartColumn({
    rows,
    scrubT,
    scrubRow,
}: {
    rows: TelemetryRow[];
    scrubT: number | null;
    scrubRow: TelemetryRow | null;
}) {
    /* Only render a chart row if at least one packet carried that field —
     * keeps curated flights (no power/RF) from showing empty axes. */
    const has = (getY: (r: TelemetryRow) => number | null) =>
        rows.some((r) => getY(r) !== null && Number.isFinite(getY(r) as number));

    return (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, background: 'var(--sl-bg)' }}>
            <div
                style={{
                    padding: '12px 16px 8px',
                    borderBottom: '1px solid var(--sl-border)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    flexShrink: 0,
                }}
            >
                <span className="sl-label-xs">SYNCHRONIZED TELEMETRY</span>
                <span className="sl-pill dim" style={{ marginLeft: 'auto' }}>
                    {rows.length} packets
                </span>
            </div>
            <div style={{ flex: 1, padding: '4px 16px', overflowY: 'auto', minHeight: 0 }}>
                {rows.length < 2 ? (
                    <div
                        style={{
                            height: 200,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'var(--sl-text-dim2)',
                            fontSize: 12,
                            letterSpacing: '0.10em',
                            textTransform: 'uppercase',
                        }}
                    >
                        Not enough packets to chart
                    </div>
                ) : (
                    <>
                        <ChartRow title="ALT (GPS)" unit="m" color="var(--sl-ok)" rows={rows} getY={(r) => r.alt} scrubT={scrubT}
                            value={scrubRow?.alt !== null && scrubRow?.alt !== undefined ? `${scrubRow.alt.toFixed(0)} m` : '—'} />
                        <ChartRow title="ALT (PRES)" unit="m" color="var(--sl-ok)" rows={rows} getY={(r) => r.presAlt} scrubT={scrubT}
                            value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                        <ChartRow title="TEMPERATURE" unit="°C" color="var(--sl-alert)" rows={rows} getY={(r) => r.temp} scrubT={scrubT}
                            value={scrubRow?.temp !== null && scrubRow?.temp !== undefined ? `${scrubRow.temp.toFixed(1)} °C` : '—'} />
                        <ChartRow title="PRESSURE" unit="hPa" color="var(--sl-neutral)" rows={rows} getY={(r) => r.pres} scrubT={scrubT}
                            value={fmtPressure(scrubRow?.pres ?? null)} />
                        {has((r) => r.batt) && (
                            <ChartRow title="BATTERY" unit="V" color="var(--sl-ok-mute)" rows={rows} getY={(r) => r.batt} scrubT={scrubT} min={3.0} max={5.5}
                                value={scrubRow?.batt !== null && scrubRow?.batt !== undefined ? `${scrubRow.batt.toFixed(2)} V` : '—'} />
                        )}
                        {has((r) => r.sol) && (
                            <ChartRow title="SOLAR" unit="V" color="var(--sl-ok-mute)" rows={rows} getY={(r) => r.sol} scrubT={scrubT} min={0} max={6}
                                value={scrubRow?.sol !== null && scrubRow?.sol !== undefined ? `${scrubRow.sol.toFixed(2)} V` : '—'} />
                        )}
                        {has((r) => r.lux) && (
                            <ChartRow title="AMBIENT LUX" unit="lx" color="var(--sl-neutral)" rows={rows} getY={(r) => r.lux} scrubT={scrubT}
                                value={scrubRow?.lux !== null && scrubRow?.lux !== undefined ? `${scrubRow.lux.toLocaleString()} lx` : '—'} />
                        )}
                        {has((r) => r.rssi) && (
                            <ChartRow title="RSSI" unit="dBm" color="var(--sl-ok-mute)" rows={rows} getY={(r) => r.rssi} scrubT={scrubT}
                                value={scrubRow?.rssi !== null && scrubRow?.rssi !== undefined ? `${scrubRow.rssi.toFixed(0)} dBm` : '—'} />
                        )}
                        {has((r) => r.snr) && (
                            <ChartRow title="SNR" unit="dB" color="var(--sl-ok-mute)" rows={rows} getY={(r) => r.snr} scrubT={scrubT}
                                value={scrubRow?.snr !== null && scrubRow?.snr !== undefined ? `${scrubRow.snr.toFixed(2)} dB` : '—'} />
                        )}
                        {has((r) => r.sats) && (
                            <ChartRow title="GPS SATELLITES" unit="" color="var(--sl-ok-mute)" rows={rows} getY={(r) => r.sats} scrubT={scrubT} min={0} max={28}
                                value={scrubRow?.sats !== null && scrubRow?.sats !== undefined ? `${scrubRow.sats}` : '—'} />
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

function ChartRow({
    title,
    unit,
    color,
    rows,
    getY,
    scrubT,
    value,
    min,
    max,
}: {
    title: string;
    unit: string;
    color: string;
    rows: TelemetryRow[];
    getY: (r: TelemetryRow) => number | null;
    scrubT: number | null;
    value: string;
    min?: number;
    max?: number;
}) {
    const { ref, width } = useElementSize(420, 62);
    return (
        <div
            style={{
                display: 'grid',
                gridTemplateColumns: '96px minmax(0, 1fr) 88px',
                alignItems: 'center',
                padding: '4px 0',
                borderBottom: '1px solid var(--sl-border)',
                minWidth: 0,
            }}
        >
            <div>
                <div className="sl-label-xs" style={{ color, opacity: 0.9, fontSize: 9 }}>
                    {title}
                </div>
                <div style={{ fontSize: 10, color: 'var(--sl-text-dim3)' }}>{unit}</div>
            </div>
            <div ref={ref} style={{ minWidth: 0, overflow: 'hidden' }}>
                <Chart
                    data={rows}
                    getY={getY}
                    width={width}
                    height={60}
                    color={color}
                    padL={32}
                    padR={6}
                    padT={8}
                    padB={14}
                    yTicks={2}
                    scrubT={scrubT ?? undefined}
                    min={min}
                    max={max}
                    fill
                />
            </div>
            <div style={{ textAlign: 'right', paddingRight: 6 }}>
                <div style={{ fontSize: 14, color, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--sl-mono)', fontWeight: 500 }}>
                    {value}
                </div>
                <div style={{ fontSize: 9, color: 'var(--sl-text-dim3)' }}>AT SCRUB</div>
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Inspector column — selected packet detail + mission events
 * ────────────────────────────────────────────────────────────── */
function InspectorColumn({
    scrubRow,
    events,
    onSelect,
    meta,
}: {
    scrubRow: TelemetryRow | null;
    events: ReplayEvent[];
    onSelect: (t: number) => void;
    meta: FlightReplayMeta;
}) {
    return (
        <div style={{ background: 'var(--sl-bg)', overflow: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--sl-border)' }}>
                <div className="sl-label-xs">SELECTED PACKET</div>
                <div style={{ fontSize: 12, color: 'var(--sl-ok)', fontFamily: 'var(--sl-mono)', marginTop: 4 }}>
                    {scrubRow ? `${fmt.datetime(scrubRow.t)} UTC` : '—'}
                </div>
            </div>
            <div style={{ flex: 1, padding: '0 16px' }}>
                {scrubRow ? <PacketDetail packet={scrubRow} meta={meta} /> : <Empty />}
                <Section title={`EVENTS · ${events.length}`}>
                    {events.length === 0 ? (
                        <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)', padding: '6px 0' }}>
                            No anomalies detected.
                        </div>
                    ) : (
                        events.map((e) => (
                            <button
                                key={e.id}
                                type="button"
                                onClick={() => onSelect(e.t)}
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
                                    <span style={{ color: 'var(--sl-text-dim3)', fontFamily: 'var(--sl-mono)' }}>
                                        {fmt.time(e.t)}
                                    </span>
                                </div>
                                <div style={{ color: 'var(--sl-text-dim2)', fontSize: 10 }}>{e.detail}</div>
                            </button>
                        ))
                    )}
                </Section>
            </div>
        </div>
    );
}

function Empty() {
    return (
        <div style={{ padding: '16px 0', fontSize: 11, color: 'var(--sl-text-dim2)' }}>
            No packet at the scrub position.
        </div>
    );
}

function PacketDetail({ packet, meta }: { packet: TelemetryRow; meta: FlightReplayMeta }) {
    const accel =
        packet.ax !== null && packet.ay !== null && packet.az !== null
            ? Math.sqrt(packet.ax ** 2 + packet.ay ** 2 + packet.az ** 2)
            : null;
    return (
        <>
            <Section title="POSITION">
                <KV k="lat" v={fmt.lat(packet.lat)} accent={packet.lat !== null ? 'teal' : 'dim'} />
                <KV k="lon" v={fmt.lon(packet.lon)} accent={packet.lon !== null ? 'teal' : 'dim'} />
                <KV k="alt (gps)" v={fmt.num(packet.alt, 0)} u={packet.alt !== null ? 'm' : undefined} />
                <KV k="alt (pres)" v={packet.presAlt !== null ? fmt.num(packet.presAlt, 0) : '—'} u={packet.presAlt !== null ? 'm' : undefined} />
                <KV k="gps sats" v={fmt.num(packet.sats, 0)} />
                <KV k="speed" v={fmt.num(packet.spd, 2)} u={packet.spd !== null ? 'm/s' : undefined} />
                <KV k="heading" v={fmt.num(packet.hdg, 1)} u={packet.hdg !== null ? '°' : undefined} />
                <KV k="hdop" v={fmt.num(packet.hdop, 2)} />
            </Section>
            <Section title="POWER">
                <KV k="v_bat" v={fmt.num(packet.batt, 3)} u={packet.batt !== null ? 'V' : undefined} accent={packet.batt !== null && packet.batt < 3.5 ? 'amber' : 'teal'} />
                <KV k="v_sol" v={fmt.num(packet.sol, 3)} u={packet.sol !== null ? 'V' : undefined} />
                <KV k="power mode" v={packet.power_mode ?? '—'} />
                <KV k="uptime" v={packet.uptime_s !== null ? fmt.duration(packet.uptime_s * 1000) : '—'} />
            </Section>
            <Section title="ENVIRONMENT">
                <KV k="temp" v={fmt.num(packet.temp, 2)} u={packet.temp !== null ? '°C' : undefined} />
                <KV k="pressure" v={fmtPressure(packet.pres)} />
                <KV k="ambient lux" v={fmt.num(packet.lux, 0)} u={packet.lux !== null ? 'lx' : undefined} />
                <KV k="uv index" v={fmt.num(packet.uv, 1)} />
            </Section>
            <Section title="RF LINK">
                <KV k="rssi" v={fmt.num(packet.rssi, 0)} u={packet.rssi !== null ? 'dBm' : undefined} />
                <KV k="snr" v={fmt.num(packet.snr, 2)} u={packet.snr !== null ? 'dB' : undefined} />
                <KV k="freq" v={packet.frequency_hz !== null ? (packet.frequency_hz / 1_000_000).toFixed(1) : '—'} u={packet.frequency_hz !== null ? 'MHz' : undefined} />
                <KV k="sf" v={packet.lora_sf !== null ? `SF${packet.lora_sf}` : '—'} />
                <KV k="tx count" v={packet.tx_count !== null ? packet.tx_count.toLocaleString() : '—'} />
            </Section>
            {accel !== null && (
                <Section title="IMU">
                    <KV k="accel_x" v={fmt.num(packet.ax, 2)} u="m/s²" />
                    <KV k="accel_y" v={fmt.num(packet.ay, 2)} u="m/s²" />
                    <KV k="accel_z" v={fmt.num(packet.az, 2)} u="m/s²" />
                    <KV k="|a|" v={accel.toFixed(2)} u="m/s²" />
                </Section>
            )}
            <div style={{ padding: '10px 0 14px', fontSize: 9, color: 'var(--sl-text-dim3)' }}>
                {meta.source === 'curated' ? 'Curated sample flight' : `device ${meta.deviceId}`}
            </div>
        </>
    );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div style={{ padding: '14px 0', borderBottom: '1px solid var(--sl-border)' }}>
            <div className="sl-label-xs" style={{ marginBottom: 8 }}>
                {title}
            </div>
            {children}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Scrubber — global timeline, drives every column
 * ────────────────────────────────────────────────────────────── */
function Scrubber({
    rows,
    visibleRows,
    tStart,
    tEnd,
    scrubT,
    onScrub,
    onReset,
    range,
    onRangeChange,
}: {
    rows: TelemetryRow[];
    visibleRows: TelemetryRow[];
    tStart: number;
    tEnd: number;
    scrubT: number | null;
    onScrub: (t: number) => void;
    onReset: () => void;
    range: RangeKey;
    onRangeChange: (r: RangeKey) => void;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);

    function pickFromEvent(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        onScrub(tStart + (tEnd - tStart) * f);
    }

    const fraction = scrubT !== null && tEnd > tStart ? ((scrubT - tStart) / (tEnd - tStart)) * 100 : 100;
    const atEnd = scrubT === null || scrubT >= tEnd;

    return (
        <div style={{ borderTop: '1px solid var(--sl-border)', padding: '10px 16px', background: 'var(--sl-bg-1)', flexShrink: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sl-text-dim3)', marginBottom: 6, letterSpacing: '0.06em' }}>
                <span>{fmt.datetime(tStart)}</span>
                <span style={{ color: 'var(--sl-ok)', fontSize: 12 }}>
                    {scrubT !== null ? `${fmt.datetime(scrubT)} UTC` : `END · ${fmt.datetime(tEnd)} UTC`}
                </span>
                <span>{fmt.datetime(tEnd)}</span>
            </div>
            <div
                ref={trackRef}
                role="slider"
                tabIndex={0}
                aria-valuemin={tStart}
                aria-valuemax={tEnd}
                aria-valuenow={scrubT ?? tEnd}
                onMouseDown={(e) => {
                    pickFromEvent(e.clientX);
                    function move(ev: MouseEvent) {
                        pickFromEvent(ev.clientX);
                    }
                    function up() {
                        window.removeEventListener('mousemove', move);
                        window.removeEventListener('mouseup', up);
                    }
                    window.addEventListener('mousemove', move);
                    window.addEventListener('mouseup', up);
                }}
                onTouchMove={(e) => pickFromEvent(e.touches[0].clientX)}
                style={{ position: 'relative', height: 24, cursor: 'pointer', userSelect: 'none' }}
            >
                <div style={{ position: 'absolute', top: 11, left: 0, right: 0, height: 2, background: 'var(--sl-border-hi)' }} />
                <div style={{ position: 'absolute', top: 11, left: 0, width: `${fraction}%`, height: 2, background: 'var(--sl-ok)' }} />
                <div style={{ position: 'absolute', top: 6, left: `calc(${fraction}% - 5px)`, width: 10, height: 12, background: 'var(--sl-ok)' }} />
                <svg width="100%" height="24" style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>
                    {visibleRows.map((r, i) => {
                        const x = ((r.t - tStart) / (tEnd - tStart || 1)) * 100;
                        return <line key={i} x1={`${x}%`} y1="2" x2={`${x}%`} y2="6" stroke="var(--sl-text-dim3)" />;
                    })}
                </svg>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button
                        type="button"
                        onClick={onReset}
                        style={{
                            background: atEnd ? 'var(--sl-ok-soft)' : 'transparent',
                            border: '1px solid ' + (atEnd ? 'var(--sl-ok)' : 'var(--sl-border-hi)'),
                            color: atEnd ? 'var(--sl-ok)' : 'var(--sl-text-dim)',
                            padding: '4px 10px',
                            fontFamily: 'var(--sl-sans)',
                            fontSize: 10,
                            letterSpacing: '0.10em',
                            cursor: 'pointer',
                        }}
                    >
                        ⤓ END
                    </button>
                    <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                        {visibleRows.length} of {rows.length} packets in window
                    </span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    {(['1h', '6h', '24h', 'all'] as RangeKey[]).map((r) => (
                        <button
                            key={r}
                            type="button"
                            onClick={() => onRangeChange(r)}
                            className={'sl-pill ' + (r === range ? 'teal' : 'dim')}
                            style={{ cursor: 'pointer', background: 'none', font: 'inherit', textTransform: 'uppercase', letterSpacing: '0.10em' }}
                        >
                            {r.toUpperCase()}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
