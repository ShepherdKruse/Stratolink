/**
 * Mission Control — the single unified flight page.
 *
 * One page, three regions:
 *   - LEFT column: the monitored balloon (with a switcher) on top, then a
 *     synchronized stack of telemetry charts.
 *   - RIGHT: a Mapbox map showing gateway coverage and the balloon's flight in
 *     three states — transmitted points (dots), the flown path between them
 *     (line), and the predicted next track (dashed forecast).
 *   - BOTTOM: a full-width timeline. Scrubbing it rewinds BOTH the charts and
 *     the balloon's position on the map to the row recorded at that moment.
 *
 * Defaults to the most-recently-transmitting balloon. Selecting a landed
 * balloon replays its full mission (useTelemetry loads since-launch history).
 *
 * Data discipline: every value is a real Supabase row or '—'. No placeholders.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Chart, fmt, type TelemetryRow } from './atoms';
import { useTelemetry, type DeviceSummary } from './useTelemetry';
import { useForecastPath, type UseForecastPathResult } from './useForecastPath';
import { useElementSize, fmtPressure, fmtAltitudeM } from './shared';
import { useIsMobile } from '@/hooks/use-mobile';
import V2MissionMap, { type V2Balloon, type V2FlightPoint, type V2Gateway } from './V2MissionMap';
import { useDashboardTheme } from './dashboard-theme';
import TelemetryV3Panel from './telemetry-v3/TelemetryV3Panel';

interface FlightSummary {
    /** Span from first to last loaded packet, ms. Null when no data. */
    durationMs: number | null;
    /** Great-circle distance summed across GPS fixes, km. */
    distanceKm: number;
}

export default function MissionControlScreen() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialSelectedId = searchParams.get('device');

    const {
        devices, selectedId, setSelectedId, rows,
    } = useTelemetry({ initialSelectedId });

    const [scrubT, setScrubT] = useState<number | null>(null);
    /* Null scrub = follow the latest packet so the page behaves "live". */
    const followLive = scrubT === null;

    /* Mobile only: charts live in a pull-up drawer, hidden by default. */
    const [chartsOpen, setChartsOpen] = useState(false);

    /* The whole flight is always in view (no range zoom). */
    const visibleRows = rows;

    /* Forecast (nominal + ensemble + ellipses + future-scrub timing). */
    const forecast = useForecastPath(selectedId);

    const isMobile = useIsMobile();
    const { theme } = useDashboardTheme();

    /* scrubT may sit in the future (along the forecast); only clamp it back if
     * it falls before the first packet (e.g. on a stale carry-over). */
    useEffect(() => {
        if (visibleRows.length === 0 || followLive) return;
        const t0 = visibleRows[0].t;
        if (scrubT! < t0) setScrubT(t0);
    }, [visibleRows, scrubT, followLive]);

    /* "Now" = the latest packet; live mode parks the cursor here. */
    const packetEndT = visibleRows.length ? visibleRows[visibleRows.length - 1].t : null;
    const effectiveScrubT: number | null = followLive ? packetEndT : scrubT;
    /* In the future leg the charts hold the last real reading. */
    const isFuture = effectiveScrubT !== null && packetEndT !== null && effectiveScrubT > packetEndT;

    const scrubRow: TelemetryRow | null = useMemo(() => {
        if (!visibleRows.length || effectiveScrubT === null) return null;
        let row = visibleRows[0];
        for (const r of visibleRows) {
            if (r.t <= effectiveScrubT) row = r;
            else break;
        }
        return row;
    }, [visibleRows, effectiveScrubT]);

    const selectedDevice: DeviceSummary | null =
        selectedId ? devices.find(d => d.id === selectedId) ?? null : null;

    /* Whole-flight totals (independent of the timeline range zoom). */
    const flightSummary: FlightSummary = useMemo(() => {
        if (rows.length === 0) return { durationMs: null, distanceKm: 0 };
        const fixes = rows.filter(r => r.lat !== null && r.lon !== null) as Array<TelemetryRow & { lat: number; lon: number }>;
        let distanceKm = 0;
        for (let i = 1; i < fixes.length; i++) {
            distanceKm += haversineKm(fixes[i - 1].lat, fixes[i - 1].lon, fixes[i].lat, fixes[i].lon);
        }
        return { durationMs: rows[rows.length - 1].t - rows[0].t, distanceKm };
    }, [rows]);

    function handleSelectDevice(id: string) {
        setSelectedId(id);
        setScrubT(null);
        const params = new URLSearchParams(searchParams.toString());
        params.set('device', id);
        router.replace(`/dashboard-v2?${params.toString()}`);
    }

    /* Mobile: one vertical stack — brand, balloon card, the map (filling the
     * screen) + timeline. The charts live in a pull-up drawer so the map gets
     * the room by default. Same components as desktop, just stacked. */
    if (isMobile) {
        return (
            <div className="sl-app" data-theme={theme} style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100dvh', minHeight: 0, overflow: 'hidden' }}>
                <div className="tlm-panel" style={{ flexShrink: 0, maxHeight: '42vh', overflow: 'hidden', display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--sl-border)' }}>
                    <div className="tlm-scroll" style={{ overflowY: 'auto', minHeight: 0 }}>
                        <TelemetryV3Panel
                            device={selectedDevice}
                            devices={devices}
                            onSelect={handleSelectDevice}
                            scrubRow={scrubRow}
                            summary={flightSummary}
                            rows={rows}
                        />
                    </div>
                </div>
                <div style={{ position: 'relative', display: 'flex', flex: 1, minHeight: 0 }}>
                    <MapColumn
                        visibleRows={visibleRows}
                        scrubRow={scrubRow}
                        selectedDevice={selectedDevice}
                        forecast={forecast}
                        scrubT={effectiveScrubT}
                        isFuture={isFuture}
                        colorScheme={theme}
                    />
                    {/* Scrubber floats over the map bottom, clear of the
                      * attribution/logo row beneath it. */}
                    <div style={{ position: 'absolute', left: 12, right: 12, bottom: 40, zIndex: 6 }}>
                        <Timeline
                            visibleRows={visibleRows}
                            scrubT={scrubT}
                            onScrub={setScrubT}
                            futureEndT={forecast.endT}
                            floating
                        />
                    </div>
                </div>
                {/* Reserve the collapsed drawer handle's footprint so it never
                  * covers the charts drawer. */}
                <div style={{ height: DRAWER_HANDLE_H, flexShrink: 0 }} />
                <ChartsDrawer open={chartsOpen} onToggle={() => setChartsOpen((v) => !v)}>
                    <div className="tlm-panel tlm-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
                        <TelemetryV3Panel
                            device={selectedDevice}
                            devices={devices}
                            onSelect={handleSelectDevice}
                            scrubRow={scrubRow}
                            summary={flightSummary}
                            rows={rows}
                        />
                    </div>
                </ChartsDrawer>
            </div>
        );
    }

    return (
        <div className="sl-app" data-theme={theme} style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <main style={{
                flex: 1,
                display: 'grid',
                gridTemplateColumns: 'minmax(360px, 420px) minmax(0, 1fr)',
                minHeight: 0,
                minWidth: 0,
            }}>
                <LeftColumn
                    device={selectedDevice}
                    devices={devices}
                    onSelect={handleSelectDevice}
                    scrubRow={scrubRow}
                    summary={flightSummary}
                    visibleRows={visibleRows}
                    rows={rows}
                    scrubT={effectiveScrubT}
                />
                {/* Right side: the map fills the full height; the scrubber
                  * floats over its bottom edge as a self-contained bar. */}
                <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
                    <MapColumn
                        visibleRows={visibleRows}
                        scrubRow={scrubRow}
                        selectedDevice={selectedDevice}
                        forecast={forecast}
                        scrubT={effectiveScrubT}
                        isFuture={isFuture}
                        colorScheme={theme}
                    />
                    {/* Centered with side clearance so the Mapbox logo
                      * (bottom-left) and attribution (bottom-right) stay clear. */}
                    <div style={{ position: 'absolute', left: 104, right: 104, bottom: 44, zIndex: 6 }}>
                        <Timeline
                            visibleRows={visibleRows}
                            scrubT={scrubT}
                            onScrub={setScrubT}
                            futureEndT={forecast.endT}
                            floating
                        />
                    </div>
                </div>
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Left column — brand/connection strip, balloon switcher, charts.
 * ────────────────────────────────────────────────────────────── */
function LeftColumn({
    device, devices, onSelect, scrubRow, summary,
    visibleRows, rows, scrubT,
}: {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    summary: FlightSummary;
    visibleRows: TelemetryRow[];
    rows: TelemetryRow[];
    scrubT: number | null;
}) {
    return (
        <div
            className="tlm-panel"
            style={{
                display: 'flex',
                flexDirection: 'column',
                minHeight: 0,
                minWidth: 0,
                borderRight: '1px solid var(--t-border)',
                background: 'var(--t-panel)',
            }}
        >
            <div className="tlm-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
                <TelemetryV3Panel
                    device={device}
                    devices={devices}
                    onSelect={onSelect}
                    scrubRow={scrubRow}
                    summary={summary}
                    rows={rows}
                />
            </div>
        </div>
    );
}

/* Brand strip — STRATOLINK mark linking home. */
function BrandStrip() {
    return (
        <div style={{
            display: 'flex', alignItems: 'center',
            padding: '9px 18px', flexShrink: 0,
            borderBottom: '1px solid var(--sl-border)', background: 'var(--sl-bg-1)',
        }}>
            <a href="/" style={{
                display: 'flex', alignItems: 'center', gap: 9,
                fontFamily: 'var(--sl-mono)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--sl-text-hi)', textDecoration: 'none', cursor: 'pointer',
            }}>
                <span aria-hidden style={{ color: 'var(--sl-ok)', display: 'inline-flex' }}>
                    <svg width={18} height={18} viewBox="0 0 32 32" fill="none">
                        <rect x={14} y={4} width={4} height={4} fill="currentColor" />
                        <rect x={12} y={14} width={8} height={2} fill="currentColor" />
                        <rect x={9} y={19} width={14} height={2} fill="currentColor" />
                        <rect x={6} y={24} width={20} height={2} fill="currentColor" />
                    </svg>
                </span>
                STRATOLINK
            </a>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Charts drawer (mobile) — slides up from the bottom over the map.
 * Collapsed, only the grab handle peeks above the bottom edge.
 * ────────────────────────────────────────────────────────────── */
const DRAWER_HANDLE_H = 46;
const DRAWER_HEIGHT = '74vh';

function ChartsDrawer({ open, onToggle, children }: {
    open: boolean;
    onToggle: () => void;
    children: React.ReactNode;
}) {
    return (
        <div
            style={{
                position: 'absolute', left: 0, right: 0, bottom: 0,
                height: DRAWER_HEIGHT, zIndex: 30,
                display: 'flex', flexDirection: 'column',
                background: 'var(--sl-bg-1)',
                borderTop: '1px solid var(--sl-border)',
                boxShadow: '0 -2px 12px rgba(26, 28, 27, 0.08)',
                transform: open ? 'translateY(0)' : `translateY(calc(${DRAWER_HEIGHT} - ${DRAWER_HANDLE_H}px))`,
                transition: 'transform 0.32s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
        >
            <button
                type="button"
                onClick={onToggle}
                aria-expanded={open}
                style={{
                    flexShrink: 0, height: DRAWER_HANDLE_H,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4,
                    background: 'transparent', border: 'none', cursor: 'pointer', width: '100%',
                    padding: 0,
                }}
            >
                <span style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--sl-text-dim3)' }} />
                <span style={{
                    fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase',
                    color: 'var(--sl-text-dim2)', fontFamily: 'var(--sl-sans)',
                }}>
                    {open ? 'Hide charts ▾' : 'Charts ▴'}
                </span>
            </button>
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                {children}
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Balloon card — monitored device + switcher + scrub-time vitals.
 * ────────────────────────────────────────────────────────────── */
function BalloonCard({ device, devices, onSelect, scrubRow, summary }: {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    summary: FlightSummary;
}) {
    const hasFix = scrubRow?.lat !== null && scrubRow?.lat !== undefined;
    return (
        <div style={{
            flexShrink: 0,
            padding: '16px 18px',
            borderBottom: '1px solid var(--sl-border)',
            background: 'var(--sl-bg-1)',
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                    <div className="sl-label-xs">MONITORING</div>
                    <select
                        value={device?.id ?? ''}
                        onChange={(e) => onSelect(e.target.value)}
                        style={{
                            marginTop: 1,
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--sl-text-hi)',
                            fontFamily: 'var(--sl-mono)',
                            fontSize: 21,
                            fontWeight: 600,
                            letterSpacing: '-0.02em',
                            cursor: 'pointer',
                            padding: 0,
                            outline: 'none',
                            maxWidth: 250,
                        }}
                    >
                        {devices.length === 0 && <option value="">no devices</option>}
                        {devices.map(d => (
                            <option key={d.id} value={d.id} style={{ background: 'var(--sl-bg-2)' }}>
                                {d.callsign ?? d.id}
                            </option>
                        ))}
                    </select>
                    {device?.callsign && (
                        <div className="sl-label-sm" style={{ marginTop: 2 }}>{device.id}</div>
                    )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    <span className={'sl-pill ' + (hasFix ? 'teal' : 'amber')}>
                        {hasFix ? 'FIX VALID' : 'NO FIX'}
                    </span>
                    <span className="sl-pill dim">{device?.status ? device.status.toUpperCase() : '—'}</span>
                </div>
            </div>

            <div className="sl-label-sm" style={{ marginBottom: 12 }}>
                {device?.launchedAt ? `launched ${fmt.datetime(device.launchedAt)}` : 'not launched'}
            </div>

            <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '4px 14px',
            }}>
                <Vital label="ALT (PRES)" accent
                    value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                <Vital label="TOTAL TIME" accent
                    value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '—'} />
                <Vital label="TOTAL DIST" accent
                    value={`${Math.round(summary.distanceKm)} km`} />
            </div>
        </div>
    );
}

function Vital({ label, value, accent }: {
    label: string;
    value: React.ReactNode;
    accent?: boolean;
}) {
    return (
        <div>
            <div className="sl-label-xs">{label}</div>
            <div style={{
                fontSize: 18,
                marginTop: 4,
                fontVariantNumeric: 'tabular-nums',
                fontFamily: 'var(--sl-mono)',
                fontWeight: 500,
                letterSpacing: '-0.02em',
                color: accent ? 'var(--sl-ok)' : 'var(--sl-text-hi)',
            }}>
                {value}
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chart stack — synchronized to the scrub time.
 * ────────────────────────────────────────────────────────────── */
function ChartStack({ visibleRows, rows, scrubT, scrubRow }: {
    visibleRows: TelemetryRow[];
    rows: TelemetryRow[];
    scrubT: number | null;
    scrubRow: TelemetryRow | null;
}) {
    const tStart = visibleRows.length ? visibleRows[0].t : null;
    const tEnd   = visibleRows.length ? visibleRows[visibleRows.length - 1].t : null;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, flex: 1 }}>
            <div style={{ flex: 1, padding: '4px 14px 8px', overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                {visibleRows.length < 2 ? (
                    <div style={{
                        height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: 'var(--sl-text-dim2)', fontSize: 12, letterSpacing: '0.10em', textTransform: 'uppercase',
                    }}>
                        Awaiting telemetry packets…
                    </div>
                ) : (
                    <>
                        <ChartRow title="ALT (GPS)" unit="m" color="var(--sl-c-alt)" rows={visibleRows} getY={r => r.alt} scrubT={scrubT}
                            value={scrubRow?.alt != null ? `${scrubRow.alt.toFixed(0)} m` : '—'} />
                        <ChartRow title="ALT (PRES)" unit="m" color="var(--sl-c-alt)" rows={visibleRows} getY={r => r.presAlt} scrubT={scrubT}
                            value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                        <ChartRow title="BATTERY" unit="V" color="var(--sl-c-batt)" rows={visibleRows} getY={r => r.batt} scrubT={scrubT}
                            value={scrubRow?.batt != null ? `${scrubRow.batt.toFixed(2)} V` : '—'} min={3.0} max={5.5} />
                        <ChartRow title="SOLAR" unit="V" color="var(--sl-c-solar)" rows={visibleRows} getY={r => r.sol} scrubT={scrubT}
                            value={scrubRow?.sol != null ? `${scrubRow.sol.toFixed(2)} V` : '—'} min={0} max={6} />
                        <ChartRow title="TEMPERATURE" unit="°C" color="var(--sl-c-temp)" rows={visibleRows} getY={r => r.temp} scrubT={scrubT}
                            value={scrubRow?.temp != null ? `${scrubRow.temp.toFixed(1)} °C` : '—'} />
                        <ChartRow title="PRESSURE" unit="hPa" color="var(--sl-c-pres)" rows={visibleRows} getY={r => r.pres} scrubT={scrubT}
                            value={fmtPressure(scrubRow?.pres ?? null)} />
                        <ChartRow title="RSSI" unit="dBm" color="var(--sl-c-rf)" rows={visibleRows} getY={r => r.rssi} scrubT={scrubT}
                            value={scrubRow?.rssi != null ? `${scrubRow.rssi.toFixed(0)} dBm` : '—'} />
                        <ChartRow title="SNR" unit="dB" color="var(--sl-c-rf)" rows={visibleRows} getY={r => r.snr} scrubT={scrubT}
                            value={scrubRow?.snr != null ? `${scrubRow.snr.toFixed(1)} dB` : '—'} />
                        <ChartRow title="GPS SATELLITES" unit="" color="var(--sl-c-sats)" rows={visibleRows} getY={r => r.sats} scrubT={scrubT}
                            value={scrubRow?.sats != null ? `${scrubRow.sats}` : '—'} min={0} max={28} />
                    </>
                )}
            </div>

            {tStart !== null && tEnd !== null && (
                <div style={{
                    padding: '7px 16px 9px 40px', borderTop: '1px solid var(--sl-border)', flexShrink: 0,
                    fontSize: 10, color: 'var(--sl-text-dim2)',
                    fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                }}>
                    <span>{fmtClock(tStart)}</span>
                    <span style={{ fontFamily: 'var(--sl-sans)', letterSpacing: '0.1em', textTransform: 'uppercase', fontSize: 9, color: 'var(--sl-text-dim3)' }}>
                        {visibleRows.length} fixes over time →
                    </span>
                    <span>{fmtClock(tEnd)}</span>
                </div>
            )}
        </div>
    );
}

function ChartRow({ title, unit, color, rows, getY, scrubT, value, min, max }: {
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
    /* Measure both dimensions so each chart grows to fill its share of the
     * column height — the rows flex to fill, no gap left at the bottom. */
    const { ref, width, height } = useElementSize(360, 48);
    return (
        <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) 92px',
            alignItems: 'stretch',
            padding: '4px 0',
            borderBottom: '1px solid var(--sl-border)',
            minWidth: 0,
            flex: '1 1 0',
            minHeight: 56,
        }}>
            <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                <div className="sl-label-xs" style={{ color: 'var(--sl-text-hi)', fontSize: 9, marginBottom: 2, flexShrink: 0 }}>
                    {title}{unit && <span style={{ color: 'var(--sl-text-dim3)', marginLeft: 4 }}>{unit}</span>}
                </div>
                <div ref={ref} style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
                    <Chart
                        data={rows}
                        getY={getY}
                        width={width}
                        height={height}
                        color={color}
                        padL={40}
                        padR={6}
                        padT={8}
                        padB={8}
                        yTicks={1}
                        strokeWidth={1}
                        hideXAxis
                        tufte
                        scrubT={scrubT ?? undefined}
                        min={min}
                        max={max}
                    />
                </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-end', paddingRight: 4 }}>
                <div style={{ fontSize: 14, color: 'var(--sl-text-hi)', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--sl-mono)', fontWeight: 500 }}>
                    {value}
                </div>
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Map column — coverage + 3-state flight path + forecast.
 * ────────────────────────────────────────────────────────────── */
function MapColumn({ visibleRows, scrubRow, selectedDevice, forecast, scrubT, isFuture, colorScheme }: {
    visibleRows: TelemetryRow[];
    scrubRow: TelemetryRow | null;
    selectedDevice: DeviceSummary | null;
    forecast: UseForecastPathResult;
    scrubT: number | null;
    isFuture: boolean;
    colorScheme: 'light' | 'dark';
}) {
    const trackPoints: V2FlightPoint[] = useMemo(() => visibleRows
        .filter(r => r.lat !== null && r.lon !== null)
        .map(r => ({ lat: r.lat as number, lon: r.lon as number, t: r.t })),
        [visibleRows]);

    /* Position along the predicted nominal path at a future time, by
     * interpolating between the evenly-time-spaced path points. */
    const futurePos = useMemo<[number, number] | null>(() => {
        if (!isFuture || scrubT === null) return null;
        const { path, originT, endT } = forecast;
        if (path.length < 2 || originT === null || endT === null || endT <= originT) return null;
        const f = Math.max(0, Math.min(1, (scrubT - originT) / (endT - originT)));
        const idx = f * (path.length - 1);
        const i = Math.floor(idx);
        const frac = idx - i;
        const a = path[i];
        const b = path[Math.min(i + 1, path.length - 1)];
        return [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac];
    }, [isFuture, scrubT, forecast]);

    /* The likely (reconstructed) path with even time spacing across the
     * observed window — so scrubbing the past glides the balloon along the
     * smooth hindcast instead of the jagged raw GPS fixes. */
    const hindcastTrack: V2FlightPoint[] = useMemo(() => {
        const pts = forecast.hindcastPath;
        if (pts.length < 2 || trackPoints.length === 0) return [];
        const t0 = trackPoints[0].t;
        const t1 = trackPoints[trackPoints.length - 1].t;
        const span = t1 - t0 || 1;
        return pts.map(([lon, lat], i) => ({ lon, lat, t: t0 + (i / (pts.length - 1)) * span }));
    }, [forecast.hindcastPath, trackPoints]);

    /* Balloon glides smoothly: along the predicted path in the future, and
     * along the likely (reconstructed) path in the past / at the live edge. */
    const balloon: V2Balloon | null = useMemo(() => {
        if (!selectedDevice) return null;
        const pastTrack = hindcastTrack.length >= 2 ? hindcastTrack : trackPoints;
        const pos = futurePos
            ?? (scrubT !== null ? lerpAlongTrack(pastTrack, scrubT) : null)
            ?? (pastTrack.length ? [pastTrack[pastTrack.length - 1].lon, pastTrack[pastTrack.length - 1].lat] as [number, number] : null);
        if (!pos) return null;
        return { id: selectedDevice.id, lat: pos[1], lon: pos[0], altitude_m: futurePos ? null : (scrubRow?.alt ?? null) };
    }, [selectedDevice, scrubRow, trackPoints, hindcastTrack, futurePos, scrubT]);

    /* Gateways belong to a real past packet — hide them on the forecast leg. */
    const mapGateways: V2Gateway[] = useMemo(() => {
        const list = isFuture ? null : (scrubRow?.gateways ?? null);
        if (!list) return [];
        return list
            .filter(g => g.lat !== null && g.lon !== null)
            .map(g => ({ gateway_id: g.gateway_id, lat: g.lat as number, lon: g.lon as number, rssi: g.rssi, snr: g.snr }));
    }, [scrubRow, isFuture]);

    /* Whether this flight ever reported a receiver — constant across scrubbing,
     * so the legend stays stable even where no receiver is currently drawn. */
    const flightHasGateways = useMemo(
        () => visibleRows.some(r => (r.gateways?.length ?? 0) > 0),
        [visibleRows],
    );

    /* Gray connector from the last real fix to the dead-reckoned "now". */
    const staleLine = useMemo<Array<[number, number]> | null>(() => {
        if (!forecast.staleGps || forecast.path.length === 0 || trackPoints.length === 0) return null;
        const last = trackPoints[trackPoints.length - 1];
        return [[last.lon, last.lat], forecast.path[0]];
    }, [forecast.staleGps, forecast.path, trackPoints]);

    /* Show the forecast at the live edge and throughout the future leg; hide it
     * when scrubbed into the past, where a forward forecast is meaningless. */
    const lastPacketT = trackPoints.length ? trackPoints[trackPoints.length - 1].t : null;
    const showForecast = scrubT !== null && lastPacketT !== null && scrubT >= lastPacketT;

    return (
        <div style={{ flex: 1, position: 'relative', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
            <V2MissionMap
                balloons={balloon ? [balloon] : []}
                activeId={selectedDevice?.id ?? null}
                flightPath={trackPoints}
                playbackT={scrubRow?.t ?? null}
                projection="globe"
                gateways={mapGateways}
                showTransmitPoints
                hindcastPath={forecast.hindcastPath}
                staleLine={staleLine}
                forecastPath={showForecast ? forecast.path : []}
                forecastEnsemble={showForecast ? forecast.ensemble : []}
                forecastEllipses={showForecast ? forecast.ellipses : []}
                colorScheme={colorScheme}
            />

            <MapLegend
                hasForecast={forecast.path.length >= 2}
                hasHindcast={forecast.hindcastPath.length >= 2}
                hasGateways={flightHasGateways}
            />

            {scrubRow?.lat != null && (
                <div style={{ position: 'absolute', top: 14, left: 14, display: 'flex', gap: 6, zIndex: 1 }}>
                    <span className="sl-pill dim">
                        {(scrubRow.lat as number).toFixed(2)}°, {(scrubRow.lon as number).toFixed(2)}°
                    </span>
                </div>
            )}
        </div>
    );
}

/* Single consolidated map legend — flight-path states + gateway coverage in
 * one card (top-right). Collapsible; defaults collapsed on mobile where space
 * is tight. Rows are keyed to whether a layer EXISTS for this flight (constant
 * across scrubbing), not to its current on-screen visibility — so the legend
 * stays stable as you scrub. */
function MapLegend({ hasForecast, hasHindcast, hasGateways }: { hasForecast: boolean; hasHindcast: boolean; hasGateways: boolean }) {
    const isMobile = useIsMobile();
    /* null = follow the per-device default (collapsed on mobile); once the
     * user toggles, their explicit choice sticks. */
    const [open, setOpen] = useState<boolean | null>(null);
    const expanded = open === null ? !isMobile : open;

    /* Swatch primitives — kept visually consistent so labels align. */
    const lineSwatch = (color: string, dashed = false, w = 18) => (
        <span style={{ display: 'inline-block', width: w, height: 0, borderTop: `${dashed ? '1.5px dashed' : '2px solid'} ${color}` }} />
    );
    const boxSwatch = (fill: string, stroke: string) => (
        <span style={{ display: 'inline-block', width: 15, height: 9, background: fill, border: `1px solid ${stroke}` }} />
    );

    return (
        <div style={{
            position: 'absolute', top: 14, right: 14, zIndex: 5,
            background: 'var(--sl-overlay-bg)',
            backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)',
            border: '1px solid var(--sl-border)',
            boxShadow: 'var(--sl-shadow)',
            fontFamily: 'var(--sl-mono)', fontSize: 10.5,
            color: 'var(--sl-text)', lineHeight: 1.2, minWidth: expanded ? 168 : 0,
            overflow: 'hidden',
        }}>
            {/* title bar */}
            <button
                type="button"
                onClick={() => setOpen(!expanded)}
                aria-expanded={expanded}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    background: 'transparent', cursor: 'pointer',
                    padding: expanded ? '7px 11px' : '6px 10px',
                    borderTop: 'none', borderLeft: 'none', borderRight: 'none',
                    borderBottom: expanded ? '1px solid var(--sl-border)' : 'none',
                    fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase',
                    color: 'var(--sl-text-dim)', fontFamily: 'inherit', fontWeight: 600,
                }}
            >
                <span>Key</span>
                <span style={{ marginLeft: 'auto', color: 'var(--sl-text-dim3)', fontSize: 8 }}>{expanded ? '▾' : '▸'}</span>
            </button>

            {expanded && (
                <div style={{ padding: '8px 11px 9px' }}>
                    <LegendHeading>Flight path</LegendHeading>
                    <LegendRow
                        swatch={<span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: '#fcfcfb', border: '1.5px solid #a11515' }} />}
                        label="transmitted"
                    />
                    {hasHindcast && <LegendRow swatch={lineSwatch('#a11515')} label="likely path" />}
                    {hasForecast && <LegendRow swatch={lineSwatch('#08327d', true)} label="forecast" />}

                    <LegendHeading style={{ marginTop: 10 }}>Gateways</LegendHeading>
                    {hasGateways && (
                        <LegendRow
                            swatch={<span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#7a9b76', border: '1px solid #fcfcfb' }} />}
                            label="receiver"
                        />
                    )}
                    <LegendRow swatch={boxSwatch('rgba(90,92,98,0.10)', 'rgba(90,92,98,0.55)')} label="150 km · in range" />
                    <LegendRow swatch={lineSwatch('rgba(90,92,98,0.6)', true, 15)} label="250 km · sightline" />
                </div>
            )}
        </div>
    );
}

function LegendHeading({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
    return (
        <div style={{
            fontSize: 8.5, letterSpacing: '0.16em', textTransform: 'uppercase',
            color: 'var(--sl-text-dim3)', fontWeight: 600, marginBottom: 6, ...style,
        }}>
            {children}
        </div>
    );
}

/* Typeset key row — fixed swatch column so all labels align. */
function LegendRow({ swatch, label }: { swatch: React.ReactNode; label: string }) {
    return (
        <div style={{ display: 'grid', gridTemplateColumns: '20px 1fr', alignItems: 'center', columnGap: 9, height: 18 }}>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{swatch}</span>
            <span style={{ color: 'var(--sl-text-dim)', letterSpacing: '0.01em' }}>{label}</span>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Timeline — full-width scrubber. Drives the charts AND the map.
 * ────────────────────────────────────────────────────────────── */
function Timeline({ visibleRows, scrubT, onScrub, futureEndT, floating = false }: {
    visibleRows: TelemetryRow[];
    scrubT: number | null;
    /* null re-arms "follow live" — the page tracks each new packet. */
    onScrub: (t: number | null) => void;
    /* Forecast horizon end; the bar extends here so the cursor can ride the
     * predicted path into the future. Null = no forecast, bar ends at "now". */
    futureEndT: number | null;
    /* When true, render as a self-contained floating card (overlaid on the
     * map) instead of a full-width bottom row. */
    floating?: boolean;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    /* When there are no rows yet we need a "now" for the empty rail. Reading
     * Date.now() during render is non-deterministic across SSR/hydration (the
     * two clocks differ by a few hundred ms), which mismatches the slider's
     * aria-value* timestamps. So fall back to 0 until mounted, then fill in the
     * real clock client-side. Once telemetry arrives this path is never taken. */
    /* A ticking real-time clock. null on the server + first client render (so
     * hydration matches), then the live time once mounted; refreshed so the
     * "live" marker creeps along the forecast as real time passes. */
    const [clientNow, setClientNow] = useState<number | null>(null);
    useEffect(() => {
        setClientNow(Date.now());
        const id = setInterval(() => setClientNow(Date.now()), 30_000);
        return () => clearInterval(id);
    }, []);
    const nowBase = clientNow ?? 0;
    const tStart = visibleRows.length ? visibleRows[0].t : nowBase - 24 * 3600 * 1000;
    /* Last real packet — the default load point and the boundary between
     * observed track (red) and forecast (blue). NOT "live". */
    const packetEndT = visibleRows.length ? visibleRows[visibleRows.length - 1].t : nowBase;
    /* "Live" = the actual current time — the balloon's projected position right
     * now. Falls back to the last packet until the clock mounts. */
    const liveT = clientNow ?? packetEndT;
    const forecastEndT = futureEndT !== null && futureEndT > packetEndT ? futureEndT : packetEndT;
    /* Rail spans far enough to include both the forecast horizon and "now". */
    const tEnd = Math.max(forecastEndT, liveT, packetEndT);
    const span = tEnd - tStart || 1;
    const hasFuture = forecastEndT > packetEndT;

    const pct = (t: number) => Math.max(0, Math.min(100, ((t - tStart) / span) * 100));
    const nowFrac = pct(packetEndT);
    const liveFrac = pct(liveT);
    const cursorT = scrubT ?? packetEndT;        // default parks the cursor at the last packet
    const fraction = pct(cursorT);
    const elapsedW = Math.min(fraction, nowFrac);

    function pickFromEvent(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const t = tStart + span * f;
        /* Snap to the last packet (re-arm follow) within 1% of that boundary. */
        if (Math.abs(t - packetEndT) <= span * 0.01) { onScrub(null); return; }
        onScrub(t);
    }

    const cursorInFuture = cursorT > packetEndT;
    /* Future leg = the forecast, which is drawn blue on the map. */
    const handleColor = cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-ok)';
    const labelLeft = Math.max(7, Math.min(93, fraction));

    /* Offset of the cursor from the real "now" (live), e.g. "+18hr" / "−5hr".
     * The default load point (last packet) reads as how stale it is, e.g.
     * "−2hr". Within a couple minutes of now it just says "live". */
    const relMs = cursorT - liveT;
    const relHr = relMs / 3_600_000;
    const relLabel = Math.abs(relMs) < 120_000
        ? 'live'
        : Math.abs(relHr) < 1
            ? `${relHr >= 0 ? '+' : '−'}${Math.max(1, Math.round(Math.abs(relHr) * 60))}m`
            : `${relHr >= 0 ? '+' : '−'}${Math.round(Math.abs(relHr))}hr`;
    const cursorIsLive = Math.abs(relMs) < 120_000;

    const onMouseDown = (e: React.MouseEvent) => {
        pickFromEvent(e.clientX);
        function move(ev: MouseEvent) { pickFromEvent(ev.clientX); }
        function up() {
            window.removeEventListener('mousemove', move);
            window.removeEventListener('mouseup', up);
        }
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
    };
    const onTouchMove = (e: React.TouchEvent) => pickFromEvent(e.touches[0].clientX);

    /* ── Floating: one slim row — state dot + clock (key info) + the track. ── */
    if (floating) {
        const PAPER = 'var(--sl-chrome-paper)';
        return (
            <div style={{
                display: 'flex', alignItems: 'center', gap: 13,
                height: 32, padding: '0 15px',
                background: 'var(--sl-overlay-bg-blur)',
                backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
                border: '1px solid var(--sl-border)',
                borderRadius: 999,
                boxShadow: '0 1px 5px rgba(26, 28, 27, 0.10)',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexShrink: 0 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: handleColor, flexShrink: 0 }} />
                    <span style={{
                        fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 11, fontWeight: 500,
                        color: cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-hi)', whiteSpace: 'nowrap',
                    }}>
                        {fmtClock(cursorT)}
                        <span style={{ color: cursorIsLive ? 'var(--sl-ok)' : cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-dim2)', marginLeft: 5 }}>
                            {relLabel}
                        </span>
                    </span>
                </div>
                <div
                    ref={trackRef}
                    className="sl-scrub-track"
                    role="slider"
                    tabIndex={0}
                    aria-valuemin={tStart}
                    aria-valuemax={tEnd}
                    aria-valuenow={cursorT}
                    onMouseDown={onMouseDown}
                    onTouchMove={onTouchMove}
                    style={{ position: 'relative', flex: 1, alignSelf: 'stretch', userSelect: 'none' }}
                >
                    {/* recessed rail groove — reads as a slider track */}
                    <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: 0, right: 0, height: 4, borderRadius: 2, background: 'var(--sl-bg-2)', border: '1px solid var(--sl-border)' }} />
                    {/* forecast horizon — dashed extension on the rail */}
                    {hasFuture && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 0.5px)', left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 0, borderTop: '1.5px dashed var(--sl-forecast-dashed)' }} />
                    )}
                    {/* elapsed fill */}
                    <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: 0, width: `${elapsedW}%`, height: 4, borderRadius: 2, background: 'var(--sl-ok)' }} />
                    {fraction > nowFrac && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 4, borderRadius: 2, background: 'var(--sl-forecast)' }} />
                    )}
                    {/* last-transmission notch — boundary between observed track
                      * and forecast. */}
                    {hasFuture && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 3px)', left: `calc(${nowFrac}% - 3px)`, width: 6, height: 6, borderRadius: '50%', background: PAPER, border: '1px solid var(--sl-text-dim2)' }} />
                    )}
                    {/* live marker — the real current time on the rail */}
                    {liveFrac > nowFrac + 0.2 && (
                        <>
                            <div style={{ position: 'absolute', top: 'calc(50% - 8px)', left: `calc(${liveFrac}% - 0.75px)`, width: 1.5, height: 16, background: 'var(--sl-ok)', borderRadius: 1 }} />
                            <div style={{ position: 'absolute', top: 'calc(50% - 11px)', left: `calc(${liveFrac}% - 2px)`, width: 4, height: 4, borderRadius: '50%', background: 'var(--sl-ok)' }} />
                        </>
                    )}
                    {/* draggable thumb — a clear capsule grip */}
                    <div
                        className="sl-scrub-thumb"
                        style={{
                            position: 'absolute', top: 'calc(50% - 9px)', left: `calc(${fraction}% - 4px)`,
                            width: 8, height: 18, borderRadius: 4,
                            background: handleColor, border: `2px solid ${PAPER}`,
                            boxShadow: '0 1px 3px rgba(26, 28, 27, 0.25)',
                        }}
                    />
                </div>
            </div>
        );
    }

    /* ── Inline (mobile): stacked track + start/end stamps. ── */
    return (
        <div style={{
            borderTop: '1px solid var(--sl-border)',
            padding: '8px 20px 9px',
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <div
                ref={trackRef}
                role="slider"
                tabIndex={0}
                aria-valuemin={tStart}
                aria-valuemax={tEnd}
                aria-valuenow={cursorT}
                onMouseDown={onMouseDown}
                onTouchMove={onTouchMove}
                style={{ position: 'relative', height: 30, cursor: 'pointer', userSelect: 'none' }}
            >
                <div style={{
                    position: 'absolute', top: -1, left: `${labelLeft}%`, transform: 'translateX(-50%)',
                    fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 10.5, fontWeight: 500,
                    color: cursorIsLive ? 'var(--sl-ok)' : cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-hi)', whiteSpace: 'nowrap', pointerEvents: 'none',
                }}>
                    {fmtClock(cursorT)} · {relLabel}
                </div>
                <div style={{ position: 'absolute', top: 22, left: 0, right: 0, height: 1, background: 'var(--sl-border-hi)' }} />
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 21.5, left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 0, borderTop: '1px dashed var(--sl-forecast-dashed)' }} />
                )}
                <div style={{ position: 'absolute', top: 21, left: 0, width: `${elapsedW}%`, height: 2, background: 'var(--sl-ok)' }} />
                {fraction > nowFrac && (
                    <div style={{ position: 'absolute', top: 21, left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 2, background: 'var(--sl-forecast)' }} />
                )}
                <svg width="100%" height="30" style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>
                    {visibleRows.map((r, i) => (
                        <line key={i} x1={`${pct(r.t)}%`} y1="25" x2={`${pct(r.t)}%`} y2="28" stroke="var(--sl-text-dim3)" strokeOpacity="0.55" />
                    ))}
                </svg>
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 19.5, left: `calc(${nowFrac}% - 2.5px)`, width: 5, height: 5, borderRadius: '50%', background: 'var(--sl-bg-1)', border: '1px solid var(--sl-text-dim2)' }} />
                )}
                {/* live marker — the real current time on the rail */}
                {liveFrac > nowFrac + 0.2 && (
                    <div style={{ position: 'absolute', top: 16, left: `calc(${liveFrac}% - 0.75px)`, width: 1.5, height: 9, background: 'var(--sl-ok)', borderRadius: 1 }} />
                )}
                <div style={{ position: 'absolute', top: 13, left: `calc(${fraction}% - 0.5px)`, width: 1, height: 16, background: handleColor }} />
                <div style={{ position: 'absolute', top: 18.5, left: `calc(${fraction}% - 3.5px)`, width: 7, height: 7, borderRadius: '50%', background: handleColor, border: '1.5px solid var(--sl-bg-1)' }} />
            </div>
            <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 3,
                fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 10, color: 'var(--sl-text-dim3)',
            }}>
                <span>{fmtClock(tStart)}</span>
                <span style={{ fontFamily: 'var(--sl-sans)', letterSpacing: '0.14em', textTransform: 'uppercase', fontSize: 8.5, color: 'var(--sl-text-dim2)' }}>
                    drag to replay{hasFuture ? ' · → forecast' : ''}
                </span>
                <span>{fmtClock(tEnd)}</span>
            </div>
        </div>
    );
}

/* Compact UTC clock without seconds, e.g. "05-29 18:55". */
function fmtClock(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/* Position [lon, lat] along a time-stamped track at time t, linearly
 * interpolated between the bracketing fixes so the balloon glides. */
function lerpAlongTrack(track: V2FlightPoint[], t: number): [number, number] | null {
    if (track.length === 0) return null;
    if (t <= track[0].t) return [track[0].lon, track[0].lat];
    const last = track[track.length - 1];
    if (t >= last.t) return [last.lon, last.lat];
    for (let i = 1; i < track.length; i++) {
        const a = track[i - 1];
        const b = track[i];
        if (t <= b.t) {
            const f = (t - a.t) / ((b.t - a.t) || 1);
            return [a.lon + (b.lon - a.lon) * f, a.lat + (b.lat - a.lat) * f];
        }
    }
    return [last.lon, last.lat];
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}
