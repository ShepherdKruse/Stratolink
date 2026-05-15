/**
 * Stratolink dashboard v2 — Mission Control screen.
 *
 * The compositional layout for the redesigned dashboard. This is the only
 * screen wired up so far; build the others (Pre-Launch, Mission Planner,
 * Device Tracker, Telemetry Lab) in the same vocabulary by reusing the atoms
 * in ./atoms.tsx and the data hook in ./useTelemetry.ts.
 *
 * Design rules (carried over from the source mockup):
 *   - Two-color palette only: --sl-ok and --sl-alert.
 *   - Mono font for numbers, sans for labels.
 *   - Flat fills, single-pixel low-opacity borders, no glow.
 *   - Every value is real or '—'. No Math.random, no hardcoded firmware.
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import {
    Age, CadenceStrip, Chart, Chrome, FreshnessBar, KPI, KV,
    MapView, Panel, Sparkline, fmt, staleness,
    type TelemetryRow,
} from './atoms';
import { useTelemetry, type DeviceSummary } from './useTelemetry';

/* Kick the "now" tick once a second so age labels keep counting up. */
function useTickingNow(intervalMs = 1000): number {
    const [now, setNow] = useState<number>(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), intervalMs);
        return () => clearInterval(id);
    }, [intervalMs]);
    return now;
}

const TABS = ['Pre-Launch', 'Planner', 'Mission Control', 'Devices', 'Lab'];

export default function MissionControlScreen() {
    const now = useTickingNow();
    const { devices, selectedId, setSelectedId, rows, deviceInfo, status, lastFetchedAt } = useTelemetry();

    /* All derived state below is recomputed any time `rows` or `now` updates,
     * so freshness labels never go stale relative to the rendered values. */
    const latest = rows.length ? rows[rows.length - 1] : null;
    const lastFixRow = useMemo(
        () => [...rows].reverse().find(r => r.lat !== null && r.lon !== null) ?? null,
        [rows],
    );

    const selectedDevice: DeviceSummary | null =
        selectedId ? devices.find(d => d.id === selectedId) ?? null : null;

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
            <Chrome
                tabs={TABS}
                active="Mission Control"
                version={deviceInfo?.firmware ?? undefined}
                lastUplinkT={latest?.t ?? null}
                lastFixT={lastFixRow?.t ?? null}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={lastFetchedAt} now={now} />
                        <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                            UTC <span style={{ color: 'var(--sl-text)' }}>{fmt.datetime(now)}</span>
                        </span>
                        <a
                            href="/dashboard"
                            style={{
                                fontSize: 10,
                                letterSpacing: '0.10em',
                                textTransform: 'uppercase',
                                color: 'var(--sl-text-dim2)',
                                textDecoration: 'none',
                                border: '1px solid var(--sl-border-hi)',
                                padding: '4px 8px',
                            }}
                        >
                            ← v1
                        </a>
                    </>
                }
            />

            <main
                style={{
                    flex: 1,
                    display: 'grid',
                    gridTemplateColumns: '280px 1fr 360px',
                    gap: 1,
                    background: 'var(--sl-border)',
                    minHeight: 0,
                }}
            >
                {/* Left rail: fleet roster */}
                <aside style={{ background: 'var(--sl-bg)', overflow: 'auto' }}>
                    <FleetRoster
                        devices={devices}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        now={now}
                    />
                </aside>

                {/* Center: KPIs, map, chart strip */}
                <section
                    style={{
                        background: 'var(--sl-bg)',
                        display: 'grid',
                        gridTemplateRows: 'auto auto 1fr auto',
                        gap: 1,
                        minWidth: 0,
                    }}
                >
                    <KpiBar latest={latest} rows={rows} lastFixT={lastFixRow?.t ?? null} now={now} />
                    <MapPanel
                        rows={rows}
                        selectedDevice={selectedDevice}
                        latest={latest}
                        lastFixRow={lastFixRow}
                        now={now}
                    />
                    <ChartGrid rows={rows} />
                    <CadencePanel rows={rows} now={now} />
                </section>

                {/* Right rail: subsystem detail */}
                <aside style={{ background: 'var(--sl-bg)', overflow: 'auto' }}>
                    <SubsystemRail
                        device={selectedDevice}
                        deviceInfo={deviceInfo}
                        latest={latest}
                        lastFixRow={lastFixRow}
                        rows={rows}
                        now={now}
                    />
                </aside>
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Connection pill (chrome right side)
 * ────────────────────────────────────────────────────────────── */
function ConnectionPill({ status, lastFetchedAt, now }: {
    status: 'connecting' | 'connected' | 'disconnected' | 'error';
    lastFetchedAt: number | null;
    now: number;
}) {
    if (status === 'disconnected') {
        return <span className="sl-pill amber">SUPABASE NOT CONFIGURED</span>;
    }
    if (status === 'error') {
        return <span className="sl-pill amber">DATABASE ERROR</span>;
    }
    if (status === 'connecting' || lastFetchedAt === null) {
        return <span className="sl-pill dim">CONNECTING…</span>;
    }
    const ageS = Math.floor((now - lastFetchedAt) / 1000);
    return (
        <span className="sl-pill teal">
            LIVE · POLL {ageS}s
        </span>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Fleet roster (left rail)
 * ────────────────────────────────────────────────────────────── */
function FleetRoster({ devices, selectedId, onSelect, now }: {
    devices: DeviceSummary[];
    selectedId: string | null;
    onSelect: (id: string) => void;
    now: number;
}) {
    return (
        <Panel
            title="Fleet"
            right={<span>{devices.length}</span>}
            bodyStyle={{ padding: 0 }}
        >
            {devices.length === 0 ? (
                <div style={{ padding: 16, fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    No devices registered. Visit /claim to register your first balloon.
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: 1 }}>
                    {devices.map(d => {
                        const fresh = staleness(d.lastContactT, now);
                        const sub = d.callsign ?? d.id;
                        return (
                            <button
                                key={d.id}
                                type="button"
                                className={'sl-dev-card' + (d.id === selectedId ? ' selected' : '')}
                                onClick={() => onSelect(d.id)}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                    <span className="sl-status-dot" style={{ background: fresh.color }} />
                                    <span style={{
                                        fontFamily: 'var(--sl-mono)',
                                        fontSize: 13,
                                        fontWeight: 500,
                                        color: 'var(--sl-text-hi)',
                                    }}>
                                        {sub}
                                    </span>
                                    <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--sl-text-dim2)', textTransform: 'uppercase', letterSpacing: '0.10em' }}>
                                        {d.status}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sl-text-dim2)' }}>
                                    <span>{d.callsign ? d.id : '—'}</span>
                                    <Age t={d.lastContactT} now={now} compact dot={false} />
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </Panel>
    );
}

/* ──────────────────────────────────────────────────────────────
 * KPI bar (top of center column)
 * ────────────────────────────────────────────────────────────── */
function KpiBar({ latest, rows, lastFixT, now }: {
    latest: TelemetryRow | null;
    rows: TelemetryRow[];
    lastFixT: number | null;
    now: number;
}) {
    const altRange = rows
        .map(r => r.alt)
        .filter((v): v is number => v !== null && Number.isFinite(v));
    const altPeak = altRange.length ? Math.max(...altRange) : null;
    const battRange = rows
        .map(r => r.batt)
        .filter((v): v is number => v !== null && Number.isFinite(v));
    const battTrend = battRange.length >= 2 ? battRange[battRange.length - 1] - battRange[0] : null;
    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1, background: 'var(--sl-border)' }}>
            <KpiCell>
                <KPI
                    label="Altitude"
                    value={fmt.num(latest?.alt, 0)}
                    unit={latest?.alt !== null && latest?.alt !== undefined ? 'm' : undefined}
                    sub={altPeak !== null ? `peak ${altPeak.toFixed(0)} m` : 'awaiting GPS fix'}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="Battery"
                    value={fmt.num(latest?.batt, 2)}
                    unit={latest?.batt !== null && latest?.batt !== undefined ? 'V' : undefined}
                    sub={battTrend !== null ? `${fmt.sign(battTrend, 2)} V over window` : 'no history'}
                    subKind={battTrend !== null && battTrend >= 0 ? 'up' : battTrend !== null ? 'down' : undefined}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="Solar"
                    value={fmt.num(latest?.sol, 2)}
                    unit={latest?.sol !== null && latest?.sol !== undefined ? 'V' : undefined}
                    sub={
                        latest?.lux !== null && latest?.lux !== undefined
                            ? `${fmt.num(latest.lux, 0)} lux`
                            : '—'
                    }
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="GPS"
                    value={
                        latest?.sats !== null && latest?.sats !== undefined
                            ? fmt.num(latest.sats, 0)
                            : '0'
                    }
                    unit={latest?.sats !== null && latest?.sats !== undefined ? 'sats' : undefined}
                    sub={<Age t={lastFixT} now={now} prefix="fix" dot />}
                    accent={lastFixT === null ? 'alert' : undefined}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="RSSI"
                    value={fmt.num(latest?.rssi, 0)}
                    unit={latest?.rssi !== null && latest?.rssi !== undefined ? 'dBm' : undefined}
                    sub={
                        latest?.snr !== null && latest?.snr !== undefined
                            ? `SNR ${fmt.num(latest.snr, 1)} dB`
                            : '—'
                    }
                />
            </KpiCell>
        </div>
    );
}

function KpiCell({ children }: { children: React.ReactNode }) {
    return <div style={{ background: 'var(--sl-bg)' }}>{children}</div>;
}

/* ──────────────────────────────────────────────────────────────
 * Map panel
 * ────────────────────────────────────────────────────────────── */
function MapPanel({ rows, selectedDevice, latest, lastFixRow, now }: {
    rows: TelemetryRow[];
    selectedDevice: DeviceSummary | null;
    latest: TelemetryRow | null;
    lastFixRow: TelemetryRow | null;
    now: number;
}) {
    const [width, setWidth] = useState(800);
    const [height, setHeight] = useState(380);
    useEffect(() => {
        function update() {
            const el = document.getElementById('sl-map-host');
            if (el) {
                setWidth(el.clientWidth);
                setHeight(el.clientHeight);
            }
        }
        update();
        window.addEventListener('resize', update);
        return () => window.removeEventListener('resize', update);
    }, []);

    /* Auto-zoom around the actual track, padding to a sensible minimum. */
    const { lats, lons } = useMemo(() => {
        const lats: number[] = [];
        const lons: number[] = [];
        rows.forEach(r => {
            if (r.lat !== null && r.lon !== null) {
                lats.push(r.lat);
                lons.push(r.lon);
            }
        });
        if (selectedDevice?.launchLat && selectedDevice?.launchLon) {
            lats.push(selectedDevice.launchLat);
            lons.push(selectedDevice.launchLon);
        }
        return { lats, lons };
    }, [rows, selectedDevice]);

    const haveAnyPoints = lats.length > 0;
    const minLat = haveAnyPoints ? Math.min(...lats) : 25;
    const maxLat = haveAnyPoints ? Math.max(...lats) : 55;
    const minLon = haveAnyPoints ? Math.min(...lons) : -130;
    const maxLon = haveAnyPoints ? Math.max(...lons) : -65;
    const padLat = Math.max(0.01, (maxLat - minLat) * 0.4);
    const padLon = Math.max(0.01, (maxLon - minLon) * 0.4);

    const track: Array<[number, number] | [null, null]> = rows.map(r =>
        r.lat !== null && r.lon !== null ? [r.lat, r.lon] : [null, null],
    );

    return (
        <Panel
            title="Mission Map"
            right={
                <>
                    <span style={{ color: 'var(--sl-text-dim2)' }}>{rows.filter(r => r.lat !== null).length} fixes</span>
                    <Age t={lastFixRow?.t ?? null} now={now} prefix="fix" />
                </>
            }
            bodyStyle={{ padding: 0 }}
        >
            <div id="sl-map-host" style={{ width: '100%', height: 360, position: 'relative' }}>
                {!haveAnyPoints && (
                    <div style={{
                        position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 2, pointerEvents: 'none',
                    }}>
                        <div style={{
                            padding: '8px 14px',
                            border: '1px solid var(--sl-border-hi)',
                            background: 'var(--sl-bg-2)',
                            color: 'var(--sl-text-dim)',
                            fontSize: 11,
                            letterSpacing: '0.10em',
                            textTransform: 'uppercase',
                        }}>
                            Awaiting first GPS fix
                        </div>
                    </div>
                )}
                <MapView
                    width={width}
                    height={height}
                    track={track}
                    focus={lastFixRow ? { lat: lastFixRow.lat as number, lon: lastFixRow.lon as number } : undefined}
                    label={selectedDevice?.callsign ?? selectedDevice?.id ?? undefined}
                    viewBoxLat={[minLat - padLat, maxLat + padLat]}
                    viewBoxLon={[minLon - padLon, maxLon + padLon]}
                />
                {/* "Live" badge floating in the upper-left of the map */}
                <div style={{ position: 'absolute', top: 10, left: 12 }}>
                    <Age t={latest?.t ?? null} now={now} dot prefix="uplink" />
                </div>
            </div>
        </Panel>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chart grid — altitude / pressure / temp / battery
 * ────────────────────────────────────────────────────────────── */
function ChartGrid({ rows }: { rows: TelemetryRow[] }) {
    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1, background: 'var(--sl-border)' }}>
            <ChartCell title="Altitude" unit="m" rows={rows} getY={r => r.alt} color="var(--sl-ok)" />
            <ChartCell title="Battery" unit="V" rows={rows} getY={r => r.batt} color="var(--sl-ok-mute)" />
            <ChartCell title="Pressure" unit="mbar" rows={rows} getY={r => r.pres} color="var(--sl-neutral)" />
            <ChartCell title="Temperature" unit="°C" rows={rows} getY={r => r.temp} color="var(--sl-alert)" />
        </div>
    );
}

function ChartCell({ title, unit, rows, getY, color }: {
    title: string;
    unit: string;
    rows: TelemetryRow[];
    getY: (r: TelemetryRow) => number | null;
    color: string;
}) {
    const [width, setWidth] = useState(360);
    const id = `chart-${title.toLowerCase()}`;
    useEffect(() => {
        function update() {
            const el = document.getElementById(id);
            if (el) setWidth(el.clientWidth);
        }
        update();
        window.addEventListener('resize', update);
        return () => window.removeEventListener('resize', update);
    }, [id]);

    const valid = rows.map(getY).filter((v): v is number => v !== null && Number.isFinite(v));
    const latest = valid.length ? valid[valid.length - 1] : null;

    return (
        <div style={{ background: 'var(--sl-bg)' }}>
            <Panel
                title={title}
                right={
                    <span style={{ color: 'var(--sl-text-hi)' }}>
                        {latest !== null ? `${valid.length >= 2 && Math.abs(latest) < 10 ? latest.toFixed(2) : latest.toFixed(0)} ${unit}` : '—'}
                    </span>
                }
                bodyStyle={{ padding: 0 }}
            >
                <div id={id} style={{ width: '100%', height: 130 }}>
                    {rows.length >= 2 ? (
                        <Chart
                            data={rows}
                            getY={getY}
                            width={width}
                            height={130}
                            color={color}
                            unit={unit}
                        />
                    ) : (
                        <EmptyChartPlaceholder label={`${title} — awaiting samples`} />
                    )}
                </div>
            </Panel>
        </div>
    );
}

function EmptyChartPlaceholder({ label }: { label: string }) {
    return (
        <div style={{
            height: 130, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--sl-text-dim2)', fontSize: 11, letterSpacing: '0.10em', textTransform: 'uppercase',
        }}>
            {label}
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Cadence panel — heartbeat strip across the bottom
 * ────────────────────────────────────────────────────────────── */
function CadencePanel({ rows, now }: { rows: TelemetryRow[]; now: number }) {
    const [width, setWidth] = useState(800);
    useEffect(() => {
        function update() {
            const el = document.getElementById('sl-cadence-host');
            if (el) setWidth(el.clientWidth);
        }
        update();
        window.addEventListener('resize', update);
        return () => window.removeEventListener('resize', update);
    }, []);
    const t0 = rows.length ? rows[0].t : now - 60 * 60 * 1000;
    const t1 = rows.length ? rows[rows.length - 1].t : now;
    return (
        <Panel
            title="Packet Cadence"
            right={
                <>
                    <span>{rows.length} pkts</span>
                    <span style={{ color: 'var(--sl-text-dim2)' }}>
                        {fmt.time(t0)} → {fmt.time(t1)}
                    </span>
                </>
            }
            bodyStyle={{ padding: 12 }}
        >
            <div id="sl-cadence-host" style={{ width: '100%' }}>
                <CadenceStrip data={rows} t0={t0} t1={t1} width={width} />
            </div>
        </Panel>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Subsystem rail (right column)
 * ────────────────────────────────────────────────────────────── */
function SubsystemRail({ device, deviceInfo, latest, lastFixRow, rows, now }: {
    device: DeviceSummary | null;
    deviceInfo: ReturnType<typeof useTelemetry>['deviceInfo'];
    latest: TelemetryRow | null;
    lastFixRow: TelemetryRow | null;
    rows: TelemetryRow[];
    now: number;
}) {
    const rowCount = rows.length;
    if (!device) {
        return (
            <Panel title="Selection">
                <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    Pick a device from the fleet roster.
                </div>
            </Panel>
        );
    }
    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 1, background: 'var(--sl-border)' }}>
            <Panel title="Device" right={<Age t={latest?.t ?? null} now={now} />}>
                <KV k="Callsign" v={device.callsign ?? '—'} />
                <KV k="Device ID" v={device.id} />
                <KV k="Status" v={device.status.toUpperCase()} accent={device.status === 'flying' ? 'teal' : 'dim'} />
                <KV k="Firmware" v={deviceInfo?.firmware ?? '—'} />
                <KV k="Launched" v={device.launchedAt ? fmt.datetime(device.launchedAt) : '—'} />
                <KV k="Window" v={`${rowCount} pkts`} u="last 24h" />
                <FreshnessRow label="uplink" t={latest?.t ?? null} now={now} />
                <FreshnessRow label="gps fix" t={lastFixRow?.t ?? null} now={now} />
            </Panel>

            <Panel title="Position">
                <KV k="Latitude"  v={fmt.lat(lastFixRow?.lat)} />
                <KV k="Longitude" v={fmt.lon(lastFixRow?.lon)} />
                <KV k="Altitude"  v={fmt.num(latest?.alt, 1)} u={latest?.alt !== null && latest?.alt !== undefined ? 'm' : undefined} />
                <KV k="Heading"   v={fmt.num(latest?.hdg, 1)} u={latest?.hdg !== null && latest?.hdg !== undefined ? '°' : undefined} />
                <KV k="Speed"     v={fmt.num(latest?.spd, 2)} u={latest?.spd !== null && latest?.spd !== undefined ? 'm/s' : undefined} />
                <KV k="HDOP"      v={fmt.num(latest?.hdop, 2)} />
                <KV k="Sats"      v={fmt.num(latest?.sats, 0)} />
            </Panel>

            <Panel title="Power">
                <KV k="Battery"  v={fmt.num(latest?.batt, 3)} u={latest?.batt !== null && latest?.batt !== undefined ? 'V' : undefined}
                    accent={latest?.batt !== null && latest?.batt !== undefined && latest.batt < 3.5 ? 'amber' : 'teal'} />
                <KV k="Solar"    v={fmt.num(latest?.sol, 3)} u={latest?.sol !== null && latest?.sol !== undefined ? 'V' : undefined} />
                <KV k="Power Mode" v={latest?.power_mode ?? '—'} />
                <KV k="Sleep" v={fmt.num(latest?.sleep_ms, 0)} u={latest?.sleep_ms !== null && latest?.sleep_ms !== undefined ? 'ms' : undefined} />
                <KV k="Uptime" v={latest?.uptime_s !== null && latest?.uptime_s !== undefined ? fmt.duration(latest.uptime_s * 1000) : '—'} />
            </Panel>

            <Panel title="Environment">
                <KV k="Temp" v={fmt.num(latest?.temp, 1)} u={latest?.temp !== null && latest?.temp !== undefined ? '°C' : undefined} />
                <KV k="Pressure" v={fmt.num(latest?.pres, 0)} u={latest?.pres !== null && latest?.pres !== undefined ? 'mbar' : undefined} />
                <KV k="Lux" v={fmt.num(latest?.lux, 0)} />
                <KV k="UV Index" v={fmt.num(latest?.uv, 1)} />
            </Panel>

            <Panel title="IMU">
                <KV k="Accel X" v={fmt.num(latest?.ax, 2)} u={latest?.ax !== null && latest?.ax !== undefined ? 'm/s²' : undefined} />
                <KV k="Accel Y" v={fmt.num(latest?.ay, 2)} u={latest?.ay !== null && latest?.ay !== undefined ? 'm/s²' : undefined} />
                <KV k="Accel Z" v={fmt.num(latest?.az, 2)} u={latest?.az !== null && latest?.az !== undefined ? 'm/s²' : undefined} />
                <KV k="Vel X"   v={fmt.num(latest?.vx, 3)} u={latest?.vx !== null && latest?.vx !== undefined ? 'm/s' : undefined} />
                <KV k="Vel Y"   v={fmt.num(latest?.vy, 3)} u={latest?.vy !== null && latest?.vy !== undefined ? 'm/s' : undefined} />
            </Panel>

            <Panel title="Radio">
                <KV k="RSSI" v={fmt.num(latest?.rssi, 0)} u={latest?.rssi !== null && latest?.rssi !== undefined ? 'dBm' : undefined} />
                <KV k="SNR"  v={fmt.num(latest?.snr, 2)} u={latest?.snr !== null && latest?.snr !== undefined ? 'dB' : undefined} />
                <KV k="Frequency" v={
                    latest?.frequency_hz !== null && latest?.frequency_hz !== undefined
                        ? (latest.frequency_hz / 1_000_000).toFixed(1)
                        : '—'
                } u={latest?.frequency_hz !== null && latest?.frequency_hz !== undefined ? 'MHz' : undefined} />
                <KV k="Spreading" v={
                    latest?.lora_sf !== null && latest?.lora_sf !== undefined
                        ? `SF${latest.lora_sf}`
                        : '—'
                } />
                <KV k="Bandwidth" v={
                    latest?.lora_bw !== null && latest?.lora_bw !== undefined
                        ? `${(latest.lora_bw / 1000).toFixed(0)}`
                        : '—'
                } u={latest?.lora_bw !== null && latest?.lora_bw !== undefined ? 'kHz' : undefined} />
                <KV k="TX Count" v={fmt.num(latest?.tx_count, 0)} />
            </Panel>

            <Panel
                title="Recent Trends"
                bodyStyle={{ padding: 12 }}
            >
                <TrendRow label="Altitude" rows={rows} getY={r => r.alt} unit="m" />
                <TrendRow label="Battery"  rows={rows} getY={r => r.batt} unit="V" />
                <TrendRow label="Solar"    rows={rows} getY={r => r.sol} unit="V" />
                <TrendRow label="Temp"     rows={rows} getY={r => r.temp} unit="°C" />
                <TrendRow label="RSSI"     rows={rows} getY={r => r.rssi} unit="dBm" />
            </Panel>
        </div>
    );
}

function TrendRow({ label, rows, getY, unit }: {
    label: string;
    rows: TelemetryRow[];
    getY: (r: TelemetryRow) => number | null;
    unit?: string;
}) {
    const valid = rows.map(getY).filter((v): v is number => v !== null && Number.isFinite(v));
    const value = valid.length ? valid[valid.length - 1] : null;
    return (
        <div className="sl-metric-row">
            <span className="name">{label}</span>
            <Sparkline data={rows.map(getY)} width={140} height={20} />
            <span className="val">
                {value !== null ? value.toFixed(Math.abs(value) < 10 ? 2 : 0) : '—'}
                {value !== null && unit ? <span style={{ color: 'var(--sl-text-dim3)', marginLeft: 4, fontSize: 10 }}>{unit}</span> : null}
            </span>
        </div>
    );
}

function FreshnessRow({ label, t, now }: { label: string; t: number | null; now: number }) {
    return (
        <div className="sl-kv-row">
            <span className="k">{label}</span>
            <span className="v" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                <FreshnessBar t={t} now={now} />
                <Age t={t} now={now} compact dot={false} />
            </span>
        </div>
    );
}
