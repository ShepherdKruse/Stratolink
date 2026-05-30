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
            <div className="sl-app" style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100dvh', minHeight: 0, overflow: 'hidden' }}>
                <BrandStrip />
                <BalloonCard
                    device={selectedDevice}
                    devices={devices}
                    onSelect={handleSelectDevice}
                    scrubRow={scrubRow}
                    summary={flightSummary}
                />
                <div style={{ position: 'relative', display: 'flex', flex: 1, minHeight: 0 }}>
                    <MapColumn
                        visibleRows={visibleRows}
                        scrubRow={scrubRow}
                        selectedDevice={selectedDevice}
                        forecast={forecast}
                        scrubT={effectiveScrubT}
                        isFuture={isFuture}
                    />
                </div>
                <Timeline
                    visibleRows={visibleRows}
                    scrubT={scrubT}
                    onScrub={setScrubT}
                    futureEndT={forecast.endT}
                />
                {/* Reserve the collapsed drawer handle's footprint so it never
                  * covers the timeline. */}
                <div style={{ height: DRAWER_HANDLE_H, flexShrink: 0 }} />
                <ChartsDrawer open={chartsOpen} onToggle={() => setChartsOpen((v) => !v)}>
                    <ChartStack
                        visibleRows={visibleRows}
                        rows={rows}
                        scrubT={effectiveScrubT}
                        scrubRow={scrubRow}
                    />
                </ChartsDrawer>
            </div>
        );
    }

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
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
                {/* Right side: map fills the height, timeline pinned beneath
                  * it — so the scrubber spans only the map, not the left
                  * column (which stays full-height). */}
                <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
                    <MapColumn
                        visibleRows={visibleRows}
                        scrubRow={scrubRow}
                        selectedDevice={selectedDevice}
                        forecast={forecast}
                        scrubT={effectiveScrubT}
                        isFuture={isFuture}
                    />
                    <Timeline
                        visibleRows={visibleRows}
                        scrubT={scrubT}
                        onScrub={setScrubT}
                        futureEndT={forecast.endT}
                    />
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
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            minWidth: 0,
            borderRight: '1px solid var(--sl-border)',
            background: 'var(--sl-bg)',
        }}>
            <BrandStrip />
            <BalloonCard
                device={device}
                devices={devices}
                onSelect={onSelect}
                scrubRow={scrubRow}
                summary={summary}
            />
            <ChartStack
                visibleRows={visibleRows}
                rows={rows}
                scrubT={scrubT}
                scrubRow={scrubRow}
            />
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
                display: 'flex', alignItems: 'center', gap: 8,
                fontFamily: 'var(--sl-mono)', fontSize: 12, letterSpacing: '0.14em', color: 'var(--sl-text)',
                textDecoration: 'none', cursor: 'pointer',
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
                boxShadow: '0 -10px 28px rgba(0, 0, 0, 0.45)',
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
                            marginTop: 2,
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--sl-ok)',
                            fontFamily: 'var(--sl-mono)',
                            fontSize: 20,
                            fontWeight: 500,
                            cursor: 'pointer',
                            padding: 0,
                            outline: 'none',
                            maxWidth: 220,
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
                <Vital label="TOTAL TIME"
                    value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '—'} />
                <Vital label="TOTAL DIST"
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
                fontSize: 15,
                marginTop: 4,
                fontVariantNumeric: 'tabular-nums',
                fontFamily: 'var(--sl-mono)',
                color: accent ? 'var(--sl-ok)' : 'var(--sl-text)',
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
                        <ChartRow title="ALT (GPS)" unit="m" color="var(--sl-ok)" rows={visibleRows} getY={r => r.alt} scrubT={scrubT}
                            value={scrubRow?.alt != null ? `${scrubRow.alt.toFixed(0)} m` : '—'} />
                        <ChartRow title="ALT (PRES)" unit="m" color="var(--sl-ok)" rows={visibleRows} getY={r => r.presAlt} scrubT={scrubT}
                            value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                        <ChartRow title="BATTERY" unit="V" color="var(--sl-ok-mute)" rows={visibleRows} getY={r => r.batt} scrubT={scrubT}
                            value={scrubRow?.batt != null ? `${scrubRow.batt.toFixed(2)} V` : '—'} min={3.0} max={5.5} />
                        <ChartRow title="SOLAR" unit="V" color="var(--sl-ok-mute)" rows={visibleRows} getY={r => r.sol} scrubT={scrubT}
                            value={scrubRow?.sol != null ? `${scrubRow.sol.toFixed(2)} V` : '—'} min={0} max={6} />
                        <ChartRow title="TEMPERATURE" unit="°C" color="var(--sl-alert)" rows={visibleRows} getY={r => r.temp} scrubT={scrubT}
                            value={scrubRow?.temp != null ? `${scrubRow.temp.toFixed(1)} °C` : '—'} />
                        <ChartRow title="PRESSURE" unit="hPa" color="var(--sl-neutral)" rows={visibleRows} getY={r => r.pres} scrubT={scrubT}
                            value={fmtPressure(scrubRow?.pres ?? null)} />
                        <ChartRow title="RSSI" unit="dBm" color="var(--sl-ok-mute)" rows={visibleRows} getY={r => r.rssi} scrubT={scrubT}
                            value={scrubRow?.rssi != null ? `${scrubRow.rssi.toFixed(0)} dBm` : '—'} />
                        <ChartRow title="SNR" unit="dB" color="var(--sl-ok-mute)" rows={visibleRows} getY={r => r.snr} scrubT={scrubT}
                            value={scrubRow?.snr != null ? `${scrubRow.snr.toFixed(1)} dB` : '—'} />
                        <ChartRow title="GPS SATELLITES" unit="" color="var(--sl-ok-mute)" rows={visibleRows} getY={r => r.sats} scrubT={scrubT}
                            value={scrubRow?.sats != null ? `${scrubRow.sats}` : '—'} min={0} max={28} />
                    </>
                )}
            </div>

            {tStart !== null && tEnd !== null && (
                <div style={{
                    padding: '6px 16px', borderTop: '1px solid var(--sl-border)', flexShrink: 0,
                    fontSize: 10, color: 'var(--sl-text-dim3)', letterSpacing: '0.04em',
                    display: 'flex', justifyContent: 'space-between',
                }}>
                    <span>{fmt.datetime(tStart)}</span>
                    <span>{visibleRows.length} packets</span>
                    <span>{fmt.datetime(tEnd)}</span>
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
                <div className="sl-label-xs" style={{ color, opacity: 0.9, fontSize: 9, marginBottom: 2, flexShrink: 0 }}>
                    {title}{unit && <span style={{ color: 'var(--sl-text-dim3)', marginLeft: 4 }}>{unit}</span>}
                </div>
                <div ref={ref} style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
                    <Chart
                        data={rows}
                        getY={getY}
                        width={width}
                        height={height}
                        color={color}
                        padL={32}
                        padR={6}
                        padT={6}
                        padB={14}
                        yTicks={2}
                        scrubT={scrubT ?? undefined}
                        min={min}
                        max={max}
                        fill
                    />
                </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-end', paddingRight: 4 }}>
                <div style={{ fontSize: 15, color, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--sl-mono)', fontWeight: 500 }}>
                    {value}
                </div>
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Map column — coverage + 3-state flight path + forecast.
 * ────────────────────────────────────────────────────────────── */
function MapColumn({ visibleRows, scrubRow, selectedDevice, forecast, scrubT, isFuture }: {
    visibleRows: TelemetryRow[];
    scrubRow: TelemetryRow | null;
    selectedDevice: DeviceSummary | null;
    forecast: UseForecastPathResult;
    scrubT: number | null;
    isFuture: boolean;
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
            />

            <MapLegend
                hasForecast={showForecast && forecast.path.length >= 2}
                hasHindcast={forecast.hindcastPath.length >= 2}
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
 * is tight. Rows appear only when their layer is on screen. */
function MapLegend({ hasForecast, hasHindcast }: { hasForecast: boolean; hasHindcast: boolean }) {
    const isMobile = useIsMobile();
    /* null = follow the per-device default (collapsed on mobile); once the
     * user toggles, their explicit choice sticks. */
    const [open, setOpen] = useState<boolean | null>(null);
    const expanded = open === null ? !isMobile : open;

    return (
        <div style={{
            position: 'absolute', top: 14, right: 14, zIndex: 5,
            background: 'rgba(8, 13, 23, 0.78)',
            backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)',
            border: '1px solid rgba(94, 234, 212, 0.12)', borderRadius: 4,
            padding: expanded ? '8px 10px' : '6px 9px',
            fontFamily: 'var(--sl-sans, system-ui, sans-serif)', fontSize: 10.5,
            color: 'rgba(200, 212, 232, 0.78)', lineHeight: 1.3, minWidth: expanded ? 140 : 0,
        }}>
            <button
                type="button"
                onClick={() => setOpen(!expanded)}
                aria-expanded={expanded}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                    background: 'transparent', border: 'none', cursor: 'pointer', padding: 0,
                    fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase',
                    color: 'rgba(200, 212, 232, 0.55)', fontFamily: 'inherit',
                    marginBottom: expanded ? 6 : 0,
                }}
            >
                <span>Legend</span>
                <span style={{ marginLeft: 'auto' }}>{expanded ? '▾' : '▸'}</span>
            </button>

            {!expanded ? null : (
            <>
            <LegendHeading>Flight path</LegendHeading>
            <LegendRow>
                <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: '#0b1220', border: '1.6px solid #5eead4' }} />
                transmitted
            </LegendRow>
            <LegendRow>
                <span style={{ display: 'inline-block', width: 18, height: 0, borderTop: '2px solid #5eead4' }} />
                flown path
            </LegendRow>
            {hasHindcast && (
                <LegendRow>
                    <span style={{ display: 'inline-block', width: 18, height: 0, borderTop: '2px dashed #3fb8a0' }} />
                    likely path
                </LegendRow>
            )}
            {hasForecast && (
                <>
                    <LegendRow>
                        <span style={{ display: 'inline-block', width: 18, height: 0, borderTop: '2px dashed #f59e0b' }} />
                        forecast
                    </LegendRow>
                    <LegendRow>
                        <span style={{ display: 'inline-block', width: 16, height: 9, background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.5)', borderRadius: 1 }} />
                        50 / 90% range
                    </LegendRow>
                </>
            )}

            <LegendHeading style={{ marginTop: 8 }}>Gateways</LegendHeading>
            <LegendRow>
                <span style={{ display: 'inline-block', width: 16, height: 9, background: 'rgba(94, 234, 212, 0.10)', border: '1px solid rgba(94, 234, 212, 0.55)', borderRadius: 1 }} />
                150 km · in range
            </LegendRow>
            <LegendRow>
                <span style={{ display: 'inline-block', width: 16, height: 0, borderTop: '1.5px dashed rgba(94, 234, 212, 0.6)' }} />
                250 km · line-of-sight
            </LegendRow>
            </>
            )}
        </div>
    );
}

function LegendHeading({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
    return (
        <div style={{ fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'rgba(200, 212, 232, 0.45)', marginBottom: 6, ...style }}>
            {children}
        </div>
    );
}

function LegendRow({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
            {children}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Timeline — full-width scrubber. Drives the charts AND the map.
 * ────────────────────────────────────────────────────────────── */
function Timeline({ visibleRows, scrubT, onScrub, futureEndT }: {
    visibleRows: TelemetryRow[];
    scrubT: number | null;
    /* null re-arms "follow live" — the page tracks each new packet. */
    onScrub: (t: number | null) => void;
    /* Forecast horizon end; the bar extends here so the cursor can ride the
     * predicted path into the future. Null = no forecast, bar ends at "now". */
    futureEndT: number | null;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    const tStart = visibleRows.length ? visibleRows[0].t : Date.now() - 24 * 3600 * 1000;
    /* "Now" = latest real packet. */
    const packetEndT = visibleRows.length ? visibleRows[visibleRows.length - 1].t : Date.now();
    const tEnd = futureEndT !== null && futureEndT > packetEndT ? futureEndT : packetEndT;
    const span = tEnd - tStart || 1;
    const hasFuture = tEnd > packetEndT;

    const pct = (t: number) => Math.max(0, Math.min(100, ((t - tStart) / span) * 100));
    const nowFrac = pct(packetEndT);
    const cursorT = scrubT ?? packetEndT;        // live parks the cursor at "now"
    const fraction = pct(cursorT);
    const elapsedW = Math.min(fraction, nowFrac);

    function pickFromEvent(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const t = tStart + span * f;
        /* Snap to "now" (re-arm follow-live) within 1% of the live boundary. */
        if (Math.abs(t - packetEndT) <= span * 0.01) { onScrub(null); return; }
        onScrub(t);
    }

    return (
        <div style={{
            borderTop: '1px solid var(--sl-border)',
            padding: '10px 20px 14px',
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <div style={{
                display: 'flex', justifyContent: 'space-between',
                fontSize: 11, color: 'var(--sl-text-dim3)', marginBottom: 6, letterSpacing: '0.04em',
            }}>
                <span>{fmtClock(tStart)}</span>
                <span style={{ color: scrubT !== null && cursorT > packetEndT ? '#f59e0b' : 'var(--sl-ok)' }}>
                    {fmtClock(cursorT)}
                </span>
                <span>{fmtClock(tEnd)}</span>
            </div>
            <div
                ref={trackRef}
                role="slider"
                tabIndex={0}
                aria-valuemin={tStart}
                aria-valuemax={tEnd}
                aria-valuenow={cursorT}
                onMouseDown={(e) => {
                    pickFromEvent(e.clientX);
                    function move(ev: MouseEvent) { pickFromEvent(ev.clientX); }
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
                {/* base track */}
                <div style={{ position: 'absolute', top: 11, left: 0, right: 0, height: 2, background: 'var(--sl-border-hi)' }} />
                {/* future region (forecast horizon) — faint amber band */}
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 11, left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 2, background: 'rgba(245, 158, 11, 0.25)' }} />
                )}
                {/* elapsed (real telemetry) — teal */}
                <div style={{ position: 'absolute', top: 11, left: 0, width: `${elapsedW}%`, height: 2, background: 'var(--sl-ok)' }} />
                {/* future progress (cursor in the forecast) — amber */}
                {fraction > nowFrac && (
                    <div style={{ position: 'absolute', top: 11, left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 2, background: '#f59e0b' }} />
                )}
                {/* "now" divider */}
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 5, left: `calc(${nowFrac}% - 0.5px)`, width: 1, height: 14, background: 'var(--sl-text-dim2)' }} />
                )}
                {/* handle */}
                <div style={{ position: 'absolute', top: 6, left: `calc(${fraction}% - 5px)`, width: 10, height: 12, background: cursorT > packetEndT ? '#f59e0b' : 'var(--sl-ok)' }} />
                {/* packet ticks (past only) */}
                <svg width="100%" height="24" style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>
                    {visibleRows.map((r, i) => (
                        <line key={i} x1={`${pct(r.t)}%`} y1="2" x2={`${pct(r.t)}%`} y2="6" stroke="var(--sl-text-dim3)" />
                    ))}
                </svg>
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
