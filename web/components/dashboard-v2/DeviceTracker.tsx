/**
 * Device Tracker — single-balloon synchronized telemetry timeline.
 *
 * Layout: device header strip with scrub-time metrics, then a 2-col body
 * with the map on the left and a synchronized chart stack on the right.
 * The bottom scrubber drives ALL charts — drag it to inspect any moment in
 * the last 24h. Every value is the actual Supabase row at that timestamp.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
    Age, Chart, Chrome,
    fmt,
    DASHBOARD_V2_TABS,
    type TelemetryRow,
} from './atoms';
import { useTelemetry, type DeviceSummary, type SubsystemFreshness } from './useTelemetry';
import { useTickingNow, useElementSize, ConnectionPill, V1Link, fmtPressure, fmtAltitudeM } from './shared';
import V2MissionMap, { type V2Balloon, type V2FlightPoint, type V2Gateway } from './V2MissionMap';

type RangeKey = '1h' | '6h' | '24h' | 'all';
interface TrackStats {
    distanceKm: number;
    maxAlt: number | null;
    minAlt: number | null;
    avgTemp: number | null;
    fixCount: number;
    rowCount: number;
}
const RANGE_MS: Record<RangeKey, number | null> = {
    '1h':  60 * 60 * 1000,
    '6h':  6  * 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    'all': null,
};

export default function DeviceTrackerScreen() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialSelectedId = searchParams.get('device');
    const now = useTickingNow();

    const {
        devices, selectedId, setSelectedId,
        rows, deviceInfo, freshness, status, lastFetchedAt,
    } = useTelemetry({ initialSelectedId });

    const [range, setRange] = useState<RangeKey>('all');
    const [scrubT, setScrubT] = useState<number | null>(null);
    /* When the user hasn't grabbed the scrubber yet, follow the latest packet
     * automatically so the screen behaves "live". */
    const followLive = scrubT === null;

    const visibleRows = useMemo(() => {
        if (rows.length === 0) return rows;
        const ms = RANGE_MS[range];
        if (ms === null) return rows;
        const cutoff = rows[rows.length - 1].t - ms;
        return rows.filter(r => r.t >= cutoff);
    }, [rows, range]);

    /* If the scrub time isn't in the visible window, snap it to the end. */
    useEffect(() => {
        if (visibleRows.length === 0) return;
        const t0 = visibleRows[0].t;
        const t1 = visibleRows[visibleRows.length - 1].t;
        if (followLive) return;
        if (scrubT! < t0 || scrubT! > t1) setScrubT(t1);
    }, [visibleRows, scrubT, followLive]);

    const effectiveScrubT: number | null = followLive
        ? (visibleRows.length ? visibleRows[visibleRows.length - 1].t : null)
        : scrubT;

    const scrubRow: TelemetryRow | null = useMemo(() => {
        if (!visibleRows.length || effectiveScrubT === null) return null;
        let row = visibleRows[0];
        for (const r of visibleRows) {
            if (r.t <= effectiveScrubT) row = r;
            else break;
        }
        return row;
    }, [visibleRows, effectiveScrubT]);

    const lastFixRow = useMemo(
        () => [...rows].reverse().find(r => r.lat !== null && r.lon !== null) ?? null,
        [rows],
    );
    const selectedDevice: DeviceSummary | null =
        selectedId ? devices.find(d => d.id === selectedId) ?? null : null;

    const trackStats: TrackStats = useMemo(() => {
        const fixes = visibleRows.filter(r => r.lat !== null && r.lon !== null) as Array<TelemetryRow & { lat: number; lon: number }>;
        let distanceKm = 0;
        for (let i = 1; i < fixes.length; i++) {
            distanceKm += haversineKm(fixes[i - 1].lat, fixes[i - 1].lon, fixes[i].lat, fixes[i].lon);
        }
        const alts = visibleRows.map(r => r.alt).filter((v): v is number => v !== null && Number.isFinite(v));
        const temps = visibleRows.map(r => r.temp).filter((v): v is number => v !== null && Number.isFinite(v));
        return {
            distanceKm,
            maxAlt: alts.length ? Math.max(...alts) : null,
            minAlt: alts.length ? Math.min(...alts) : null,
            avgTemp: temps.length ? temps.reduce((a, b) => a + b, 0) / temps.length : null,
            fixCount: fixes.length,
            rowCount: visibleRows.length,
        };
    }, [visibleRows]);

    function handleNavigate(path: string) {
        const url = selectedId ? `${path}?device=${encodeURIComponent(selectedId)}` : path;
        router.push(url);
    }

    function handleSelectDevice(id: string) {
        setSelectedId(id);
        setScrubT(null);
        const params = new URLSearchParams(searchParams.toString());
        params.set('device', id);
        router.replace(`/dashboard-v2/device?${params.toString()}`);
    }

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2/device"
                onNavigate={handleNavigate}
                version={deviceInfo?.firmware ?? undefined}
                lastUplinkT={rows.length ? rows[rows.length - 1].t : null}
                lastFixT={lastFixRow?.t ?? null}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={lastFetchedAt} now={now} />
                        <span style={{ fontSize: 11 }}>
                            {selectedDevice?.callsign ?? selectedDevice?.id ?? '—'}
                        </span>
                        <V1Link />
                    </>
                }
            />

            <DeviceHeaderStrip
                device={selectedDevice}
                devices={devices}
                onSelect={handleSelectDevice}
                scrubRow={scrubRow}
                lastFixRow={lastFixRow}
                freshness={freshness}
                now={now}
            />

            <main style={{
                flex: 1,
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
                minHeight: 0,
                minWidth: 0,
            }}>
                <MapColumn
                    visibleRows={visibleRows}
                    scrubRow={scrubRow}
                    selectedDevice={selectedDevice}
                    now={now}
                />
                <ChartColumn
                    visibleRows={visibleRows}
                    rows={rows}
                    scrubT={effectiveScrubT}
                    onScrub={(t) => setScrubT(t)}
                    onResetScrub={() => setScrubT(null)}
                    range={range}
                    onRangeChange={setRange}
                    scrubRow={scrubRow}
                    followLive={followLive}
                    trackStats={trackStats}
                />
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Device header strip — selector + 7 metrics
 * ────────────────────────────────────────────────────────────── */
function DeviceHeaderStrip({ device, devices, onSelect, scrubRow, lastFixRow, freshness, now }: {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    lastFixRow: TelemetryRow | null;
    freshness: SubsystemFreshness;
    now: number;
}) {
    const hasFix = scrubRow?.lat !== null && scrubRow?.lat !== undefined;
    return (
        <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--sl-border)',
            background: 'var(--sl-bg-1)',
            padding: '14px 20px',
            gap: 24,
            alignItems: 'center',
            flexShrink: 0,
            /* The seven metrics + selector can be wider than a small viewport.
             * Allow the strip itself to scroll instead of pushing the page. */
            minWidth: 0,
            overflowX: 'auto',
            scrollbarWidth: 'thin',
        }}>
            <div>
                <div className="sl-label-xs">DEVICE</div>
                <select
                    value={device?.id ?? ''}
                    onChange={(e) => onSelect(e.target.value)}
                    style={{
                        marginTop: 2,
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--sl-ok)',
                        fontFamily: 'var(--sl-mono)',
                        fontSize: 18,
                        fontWeight: 500,
                        cursor: 'pointer',
                        padding: 0,
                        outline: 'none',
                    }}
                >
                    {devices.length === 0 && <option value="">no devices</option>}
                    {devices.map(d => (
                        <option key={d.id} value={d.id} style={{ background: 'var(--sl-bg-2)' }}>
                            {d.callsign ?? d.id}
                        </option>
                    ))}
                </select>
            </div>
            <div style={{ width: 1, height: 36, background: 'var(--sl-border)' }} />

            <HeaderMetric label="POSITION" t={lastFixRow?.t ?? null} now={now}
                value={hasFix ? `${fmt.lat(scrubRow!.lat)}, ${fmt.lon(scrubRow!.lon)}` : '—'}
                size={13} />
            <HeaderMetric label="ALTITUDE" t={lastFixRow?.t ?? null} now={now} accent="teal"
                value={scrubRow?.alt !== null && scrubRow?.alt !== undefined ? scrubRow!.alt!.toFixed(0) : '—'}
                unit={scrubRow?.alt !== null && scrubRow?.alt !== undefined ? 'm' : undefined} />
            <HeaderMetric label="SPEED" t={freshness.velocity} now={now}
                value={scrubRow?.spd !== null && scrubRow?.spd !== undefined ? scrubRow!.spd!.toFixed(2) : '—'}
                unit={scrubRow?.spd !== null && scrubRow?.spd !== undefined ? 'm/s' : undefined} />
            <HeaderMetric label="HEADING" t={lastFixRow?.t ?? null} now={now}
                value={scrubRow?.hdg !== null && scrubRow?.hdg !== undefined ? `${scrubRow!.hdg!.toFixed(1)}°` : '—'} />
            <HeaderMetric label="BATTERY" t={freshness.battery} now={now}
                value={scrubRow?.batt !== null && scrubRow?.batt !== undefined ? scrubRow!.batt!.toFixed(2) : '—'}
                unit={scrubRow?.batt !== null && scrubRow?.batt !== undefined ? 'V' : undefined} />
            <HeaderMetric label="SIGNAL" t={freshness.rssi} now={now}
                value={scrubRow?.rssi !== null && scrubRow?.rssi !== undefined ? scrubRow!.rssi!.toString() : '—'}
                unit={scrubRow?.rssi !== null && scrubRow?.rssi !== undefined ? 'dBm' : undefined} />
            <HeaderMetric label="SATELLITES" t={lastFixRow?.t ?? null} now={now}
                value={scrubRow?.sats !== null && scrubRow?.sats !== undefined ? scrubRow!.sats!.toString() : '—'} />

            <div style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                <span className={'sl-pill ' + (hasFix ? 'teal' : 'amber')}>
                    {hasFix ? 'FIX VALID' : 'NO FIX AT SCRUB'}
                </span>
                <span className="sl-pill dim">
                    {device?.status ? device.status.toUpperCase() : '—'}
                </span>
            </div>
        </div>
    );
}

function HeaderMetric({ label, value, unit, t, accent, now, size }: {
    label: string;
    value: string;
    unit?: string;
    t: number | null;
    accent?: 'teal';
    now: number;
    size?: number;
}) {
    return (
        <div>
            <div className="sl-label-xs">{label}</div>
            <div style={{
                fontSize: size || 18,
                marginTop: 2,
                fontVariantNumeric: 'tabular-nums',
                fontFamily: 'var(--sl-mono)',
                color: accent === 'teal' ? 'var(--sl-ok)' : 'var(--sl-text)',
            }}>
                {value}
                {unit && <span style={{ color: 'var(--sl-text-dim3)', fontSize: 12, marginLeft: 4 }}>{unit}</span>}
            </div>
            <div style={{ marginTop: 4 }}>
                <Age t={t} now={now} compact dot />
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Map column
 * ────────────────────────────────────────────────────────────── */
function MapColumn({ visibleRows, scrubRow, selectedDevice, now }: {
    visibleRows: TelemetryRow[];
    scrubRow: TelemetryRow | null;
    selectedDevice: DeviceSummary | null;
    now: number;
}) {
    const trackPoints: V2FlightPoint[] = useMemo(() => visibleRows
        .filter(r => r.lat !== null && r.lon !== null)
        .map(r => ({ lat: r.lat as number, lon: r.lon as number, t: r.t })),
        [visibleRows]);

    /* Single balloon at the scrub time (or last fix if scrub has no fix). */
    const balloon: V2Balloon | null = useMemo(() => {
        if (!selectedDevice) return null;
        if (scrubRow && scrubRow.lat !== null && scrubRow.lon !== null) {
            return {
                id: selectedDevice.id,
                lat: scrubRow.lat,
                lon: scrubRow.lon,
                altitude_m: scrubRow.alt,
            };
        }
        const lastFix = trackPoints[trackPoints.length - 1];
        if (lastFix) {
            return {
                id: selectedDevice.id,
                lat: lastFix.lat,
                lon: lastFix.lon,
                altitude_m: scrubRow?.alt ?? null,
            };
        }
        return null;
    }, [selectedDevice, scrubRow, trackPoints]);

    /* Gateways tied to the *scrubbed* packet — so dragging the timeline
     * animates "who heard this packet at this moment". Falls back to the
     * latest packet's gateways when no scrub has happened. */
    const mapGateways: V2Gateway[] = useMemo(() => {
        const list = scrubRow?.gateways ?? null;
        if (!list) return [];
        return list
            .filter(g => g.lat !== null && g.lon !== null)
            .map(g => ({
                gateway_id: g.gateway_id,
                lat: g.lat as number,
                lon: g.lon as number,
                rssi: g.rssi,
                snr: g.snr,
            }));
    }, [scrubRow]);

    return (
        <div style={{
            position: 'relative',
            borderRight: '1px solid var(--sl-border)',
            minHeight: 0,
            minWidth: 0,
            overflow: 'hidden',
        }}>
            <V2MissionMap
                balloons={balloon ? [balloon] : []}
                activeId={selectedDevice?.id ?? null}
                flightPath={trackPoints}
                playbackT={scrubRow?.t ?? null}
                projection="mercator"
                gateways={mapGateways}
            />

            {/* Top-left badges */}
            <div style={{ position: 'absolute', top: 14, left: 14, display: 'flex', gap: 6, zIndex: 1 }}>
                <span className="sl-pill dim">MAPBOX · DARK</span>
                {scrubRow?.lat !== null && scrubRow?.lat !== undefined && (
                    <span className="sl-pill dim">
                        {scrubRow.lat.toFixed(2)}° N · {Math.abs(scrubRow.lon as number).toFixed(2)}° W
                    </span>
                )}
                <span className="sl-pill dim">
                    <Age t={scrubRow?.t ?? null} now={now} compact dot prefix="scrub" />
                </span>
            </div>
        </div>
    );
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

/* ──────────────────────────────────────────────────────────────
 * Chart column — synchronized stack
 * ────────────────────────────────────────────────────────────── */
function ChartColumn({ visibleRows, rows, scrubT, onScrub, onResetScrub, range, onRangeChange, scrubRow, followLive, trackStats }: {
    visibleRows: TelemetryRow[];
    rows: TelemetryRow[];
    scrubT: number | null;
    onScrub: (t: number) => void;
    onResetScrub: () => void;
    range: RangeKey;
    onRangeChange: (r: RangeKey) => void;
    scrubRow: TelemetryRow | null;
    followLive: boolean;
    trackStats: TrackStats;
}) {
    const tStart = visibleRows.length ? visibleRows[0].t : Date.now() - 24 * 3600 * 1000;
    const tEnd   = visibleRows.length ? visibleRows[visibleRows.length - 1].t : Date.now();
    const spanMs = tEnd - tStart;
    const spanLabel = spanMs > 0
        ? fmt.duration(spanMs)
        : '—';

    return (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
            {/* Toolbar */}
            <div style={{
                padding: '12px 16px 8px',
                borderBottom: '1px solid var(--sl-border)',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                flexShrink: 0,
            }}>
                <span className="sl-label-xs">SYNCHRONIZED TELEMETRY</span>
                <span style={{ color: 'var(--sl-text-dim2)', fontSize: 11 }}>
                    {visibleRows.length ? `${fmt.datetime(tStart)} → ${fmt.datetime(tEnd)}` : 'no data'}
                </span>
                <span className="sl-pill dim" style={{ marginLeft: 'auto' }}>
                    {visibleRows.length} packets
                </span>
                <span className="sl-pill dim">{spanLabel}</span>
            </div>

            {/* Track stats — lifted out of the map overlay so the flight path stays unobstructed */}
            <div style={{
                padding: '8px 16px',
                borderBottom: '1px solid var(--sl-border)',
                display: 'flex',
                alignItems: 'baseline',
                gap: 18,
                flexShrink: 0,
                overflowX: 'auto',
                scrollbarWidth: 'thin',
            }}>
                <span className="sl-label-xs">TRACK</span>
                <TrackStat label="distance" value={`${trackStats.distanceKm.toFixed(2)} km`} />
                <TrackStat label="max alt"  value={trackStats.maxAlt !== null ? `${trackStats.maxAlt.toFixed(0)} m` : '—'} />
                <TrackStat label="min alt"  value={trackStats.minAlt !== null ? `${trackStats.minAlt.toFixed(0)} m` : '—'} />
                <TrackStat label="avg temp" value={trackStats.avgTemp !== null ? `${trackStats.avgTemp.toFixed(1)}°C` : '—'} />
                <TrackStat label="points"   value={`${trackStats.fixCount} / ${trackStats.rowCount}`} />
            </div>

            {/* Chart stack */}
            <div style={{ flex: 1, padding: '4px 16px', overflowY: 'auto' }}>
                {visibleRows.length < 2 ? (
                    <div style={{
                        height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: 'var(--sl-text-dim2)', fontSize: 12, letterSpacing: '0.10em', textTransform: 'uppercase',
                    }}>
                        Awaiting telemetry packets…
                    </div>
                ) : (
                    <>
                        <ChartRow title="ALT (GPS)"     unit="m"   color="var(--sl-ok)"        rows={visibleRows} getY={r => r.alt}  scrubT={scrubT} value={scrubRow?.alt   !== null && scrubRow?.alt   !== undefined ? `${scrubRow!.alt!.toFixed(0)} m` : '—'} />
                        <ChartRow title="ALT (PRES)"    unit="m"   color="var(--sl-ok)"        rows={visibleRows} getY={r => r.presAlt} scrubT={scrubT} value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                        <ChartRow title="BATTERY"       unit="V"   color="var(--sl-ok-mute)"   rows={visibleRows} getY={r => r.batt} scrubT={scrubT} value={scrubRow?.batt  !== null && scrubRow?.batt  !== undefined ? `${scrubRow!.batt!.toFixed(2)} V`   : '—'} min={3.0} max={5.5} />
                        <ChartRow title="SOLAR"         unit="V"   color="var(--sl-ok-mute)"   rows={visibleRows} getY={r => r.sol}  scrubT={scrubT} value={scrubRow?.sol   !== null && scrubRow?.sol   !== undefined ? `${scrubRow!.sol!.toFixed(2)} V`    : '—'} min={0} max={6} />
                        <ChartRow title="TEMPERATURE"   unit="°C"  color="var(--sl-alert)"     rows={visibleRows} getY={r => r.temp} scrubT={scrubT} value={scrubRow?.temp  !== null && scrubRow?.temp  !== undefined ? `${scrubRow!.temp!.toFixed(1)} °C`   : '—'} />
                        <ChartRow title="PRESSURE"      unit="hPa" color="var(--sl-neutral)"   rows={visibleRows} getY={r => r.pres} scrubT={scrubT} value={fmtPressure(scrubRow?.pres ?? null)} />
                        <ChartRow title="AMBIENT LUX"   unit="lx"  color="var(--sl-neutral)"   rows={visibleRows} getY={r => r.lux}  scrubT={scrubT} value={scrubRow?.lux   !== null && scrubRow?.lux   !== undefined ? `${scrubRow!.lux!.toLocaleString()} lx` : '—'} />
                        <ChartRow title="RSSI"          unit="dBm" color="var(--sl-ok-mute)"   rows={visibleRows} getY={r => r.rssi} scrubT={scrubT} value={scrubRow?.rssi  !== null && scrubRow?.rssi  !== undefined ? `${scrubRow!.rssi!.toFixed(0)} dBm`  : '—'} />
                        <ChartRow title="SNR"           unit="dB"  color="var(--sl-ok-mute)"   rows={visibleRows} getY={r => r.snr}  scrubT={scrubT} value={scrubRow?.snr   !== null && scrubRow?.snr   !== undefined ? `${scrubRow!.snr!.toFixed(2)} dB`    : '—'} />
                        <ChartRow title="GPS SATELLITES" unit=""    color="var(--sl-ok-mute)"  rows={visibleRows} getY={r => r.sats} scrubT={scrubT} value={scrubRow?.sats !== null && scrubRow?.sats !== undefined ? `${scrubRow!.sats}` : '—'} min={0} max={28} />
                    </>
                )}
            </div>

            {/* Scrubber */}
            <Scrubber
                rows={rows}
                visibleRows={visibleRows}
                tStart={tStart}
                tEnd={tEnd}
                scrubT={scrubT}
                onScrub={onScrub}
                onResetScrub={onResetScrub}
                range={range}
                onRangeChange={onRangeChange}
                followLive={followLive}
            />
        </div>
    );
}

function TrackStat({ label, value }: { label: string; value: string }) {
    return (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
            <span style={{ fontSize: 10, color: 'var(--sl-text-dim3)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</span>
            <span style={{
                fontSize: 12,
                color: 'var(--sl-text)',
                fontFamily: 'var(--sl-mono)',
                fontVariantNumeric: 'tabular-nums',
            }}>{value}</span>
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
    const { ref, width } = useElementSize(620, 62);
    return (
        <div style={{
            display: 'grid',
            gridTemplateColumns: '110px minmax(0, 1fr) 110px',
            alignItems: 'center',
            padding: '4px 0',
            borderBottom: '1px solid var(--sl-border)',
            minWidth: 0,
        }}>
            <div>
                <div className="sl-label-xs" style={{ color, opacity: 0.9, fontSize: 9 }}>{title}</div>
                <div style={{ fontSize: 10, color: 'var(--sl-text-dim3)' }}>{unit}</div>
            </div>
            <div ref={ref} style={{ minWidth: 0, overflow: 'hidden' }}>
                <Chart
                    data={rows}
                    getY={getY}
                    width={width}
                    height={64}
                    color={color}
                    padL={34}
                    padR={8}
                    padT={8}
                    padB={14}
                    yTicks={2}
                    scrubT={scrubT ?? undefined}
                    min={min}
                    max={max}
                    fill
                />
            </div>
            <div style={{ textAlign: 'right', paddingRight: 8 }}>
                <div style={{
                    fontSize: 16,
                    color,
                    fontVariantNumeric: 'tabular-nums',
                    fontFamily: 'var(--sl-mono)',
                    fontWeight: 500,
                }}>
                    {value}
                </div>
                <div style={{ fontSize: 9, color: 'var(--sl-text-dim3)' }}>AT SCRUB</div>
            </div>
        </div>
    );
}

function Scrubber({ rows, visibleRows, tStart, tEnd, scrubT, onScrub, onResetScrub, range, onRangeChange, followLive }: {
    rows: TelemetryRow[];
    visibleRows: TelemetryRow[];
    tStart: number;
    tEnd: number;
    scrubT: number | null;
    onScrub: (t: number) => void;
    onResetScrub: () => void;
    range: RangeKey;
    onRangeChange: (r: RangeKey) => void;
    followLive: boolean;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);

    function pickFromEvent(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const t = tStart + (tEnd - tStart) * f;
        onScrub(t);
    }

    const fraction = scrubT !== null && tEnd > tStart
        ? ((scrubT - tStart) / (tEnd - tStart)) * 100
        : 100;

    return (
        <div style={{
            borderTop: '1px solid var(--sl-border)',
            padding: '10px 16px',
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 10,
                color: 'var(--sl-text-dim3)',
                marginBottom: 6,
                letterSpacing: '0.06em',
            }}>
                <span>{fmt.datetime(tStart)}</span>
                <span style={{ color: 'var(--sl-ok)', fontSize: 12 }}>
                    {scrubT !== null ? `${fmt.datetime(scrubT)} UTC` : `LIVE · ${fmt.datetime(tEnd)} UTC`}
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
                <div style={{ position: 'absolute', top: 11, left: 0, right: 0, height: 2, background: 'var(--sl-border-hi)' }} />
                <div style={{ position: 'absolute', top: 11, left: 0, width: `${fraction}%`, height: 2, background: 'var(--sl-ok)' }} />
                <div style={{
                    position: 'absolute',
                    top: 6,
                    left: `calc(${fraction}% - 5px)`,
                    width: 10, height: 12,
                    background: 'var(--sl-ok)',
                }} />
                <svg width="100%" height="24" style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>
                    {visibleRows.map((r, i) => {
                        const x = ((r.t - tStart) / (tEnd - tStart || 1)) * 100;
                        return <line key={i} x1={`${x}%`} y1="2" x2={`${x}%`} y2="6" stroke="var(--sl-text-dim3)" />;
                    })}
                </svg>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button
                        type="button"
                        onClick={onResetScrub}
                        style={ScrubControlStyle(followLive)}
                    >
                        ▶ {followLive ? 'LIVE' : 'GO LIVE'}
                    </button>
                    <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                        {visibleRows.length} of {rows.length} packets in window
                    </span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    {(['1h', '6h', '24h', 'all'] as RangeKey[]).map(r => (
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

function ScrubControlStyle(active: boolean): React.CSSProperties {
    return {
        background: active ? 'var(--sl-ok-soft)' : 'transparent',
        border: '1px solid ' + (active ? 'var(--sl-ok)' : 'var(--sl-border-hi)'),
        color: active ? 'var(--sl-ok)' : 'var(--sl-text-dim)',
        padding: '4px 10px',
        fontFamily: 'var(--sl-sans)',
        fontSize: 10,
        letterSpacing: '0.10em',
        cursor: 'pointer',
    };
}
