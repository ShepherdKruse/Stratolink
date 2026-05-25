/**
 * Stratolink dashboard v2 — Mission Control screen.
 *
 * Fleet overview with a 6-up KPI strip, fleet roster, map, and a right-rail
 * subsystem panel for the selected device.
 *
 * Data discipline: every number is a real Supabase value or '—'. No
 * Math.random, no hardcoded firmware version, no synthetic packet count.
 */
'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
    Age, CadenceStrip, Chrome, FreshnessBar, KPI, KV,
    Sparkline, fmt, staleness,
    DASHBOARD_V2_TABS,
    type TelemetryRow,
} from './atoms';
import { useTelemetry, type DeviceSummary, type FleetMetrics, type FleetAlert, type SubsystemFreshness } from './useTelemetry';
import { useTickingNow, useElementSize, ConnectionPill, V1Link, fmtPressure, fmtAltitudeM } from './shared';
import V2MissionMap, { type V2Balloon, type V2FlightPoint, type V2Gateway } from './V2MissionMap';
import GatewayCoverageLegend from './GatewayCoverageLegend';

export default function MissionControlScreen() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialSelectedId = searchParams.get('device');
    const now = useTickingNow();

    const {
        devices, selectedId, setSelectedId,
        rows, deviceInfo, freshness, fleet, alerts,
        status, lastFetchedAt,
    } = useTelemetry({ initialSelectedId });

    const latest = rows.length ? rows[rows.length - 1] : null;
    const lastFixRow = useMemo(
        () => [...rows].reverse().find(r => r.lat !== null && r.lon !== null) ?? null,
        [rows],
    );
    const selectedDevice: DeviceSummary | null =
        selectedId ? devices.find(d => d.id === selectedId) ?? null : null;

    /* Carry the selected device through tab navigation as ?device=... */
    function handleNavigate(path: string) {
        const url = selectedId ? `${path}?device=${encodeURIComponent(selectedId)}` : path;
        router.push(url);
    }

    function handleSelect(id: string) {
        setSelectedId(id);
        const params = new URLSearchParams(searchParams.toString());
        params.set('device', id);
        router.replace(`/dashboard-v2?${params.toString()}`);
    }

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2"
                onNavigate={handleNavigate}
                version={deviceInfo?.firmware ?? undefined}
                lastUplinkT={fleet.lastUplinkT ?? latest?.t ?? null}
                lastFixT={lastFixRow?.t ?? null}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={lastFetchedAt} now={now} />
                        <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                            UTC <span style={{ color: 'var(--sl-text)' }}>{fmt.datetime(now)}</span>
                        </span>
                        <V1Link />
                    </>
                }
            />

            {/* 6-KPI strip */}
            <KpiStrip
                fleet={fleet}
                now={now}
                alerts={alerts}
                missionStartedAt={selectedDevice?.launchedAt ?? null}
            />

            <main
                style={{
                    flex: 1,
                    display: 'grid',
                    gridTemplateColumns: '300px minmax(0, 1fr) 340px',
                    minHeight: 0,
                    minWidth: 0,
                    background: 'var(--sl-border)',
                    gap: 1,
                }}
            >
                {/* Left rail */}
                <aside style={{ background: 'var(--sl-bg)', overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 32 }}>
                    <FleetRoster
                        devices={devices}
                        selectedId={selectedId}
                        rowsForSelected={rows}
                        latest={latest}
                        onSelect={handleSelect}
                        now={now}
                    />
                    <SystemStatus
                        status={status}
                        latest={latest}
                        fleet={fleet}
                        lastFetchedAt={lastFetchedAt}
                    />
                </aside>

                {/* Center: map */}
                <section style={{ background: 'var(--sl-bg)', position: 'relative', minHeight: 0 }}>
                    <CenterMap
                        devices={devices}
                        rows={rows}
                        latest={latest}
                        lastFixRow={lastFixRow}
                        selectedDevice={selectedDevice}
                        now={now}
                    />
                </section>

                {/* Right rail */}
                <aside style={{ background: 'var(--sl-bg)', overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 28 }}>
                    {selectedDevice ? (
                        <>
                            <SelectedDevicePanel
                                device={selectedDevice}
                                deviceInfo={deviceInfo}
                                latest={latest}
                                lastFixRow={lastFixRow}
                                rowCount={rows.length}
                                now={now}
                            />
                            <DataFreshnessPanel freshness={freshness} now={now} />
                            <LiveMetricsPanel rows={rows} latest={latest} />
                            <GatewaysPanel latest={latest} />
                            <AlertsPanel alerts={alerts} now={now} />
                            <CadencePanel rows={rows} now={now} />
                        </>
                    ) : (
                        <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                            No device selected. Pick one from the fleet list.
                        </div>
                    )}
                </aside>
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * KPI strip — fleet-wide metrics from Supabase
 * ────────────────────────────────────────────────────────────── */
function KpiStrip({
    fleet,
    now,
    alerts,
    missionStartedAt,
}: {
    fleet: FleetMetrics;
    now: number;
    alerts: FleetAlert[];
    /** Selected device's launch time — mission clock follows activation, not rolling 24h. */
    missionStartedAt: number | null;
}) {
    const missionTimeMs =
        missionStartedAt != null ? now - missionStartedAt : fleet.firstFixT ? now - fleet.firstFixT : null;
    const missionTime = missionTimeMs !== null
        ? `${Math.floor(missionTimeMs / 3_600_000).toString().padStart(2, '0')}:${Math.floor((missionTimeMs % 3_600_000) / 60_000).toString().padStart(2, '0')}`
        : '—';
    const lockRate = fleet.gpsLockRatePct !== null ? Math.round(fleet.gpsLockRatePct).toString() : '—';
    const lockAccent = fleet.gpsLockRatePct !== null && fleet.gpsLockRatePct < 50 ? 'alert' : undefined;
    const warnCount = alerts.filter(a => a.severity === 'warn').length;
    const infoCount = alerts.filter(a => a.severity === 'info').length;
    return (
        <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)',
            borderBottom: '1px solid var(--sl-border)',
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <KpiCell>
                <KPI
                    label="ACTIVE"
                    value={fleet.activeCount.toString()}
                    sub={fleet.totalDevices > 0 ? `/ ${fleet.totalDevices} fleet` : 'no devices'}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="UPLINKS / 24h"
                    value={fleet.uplinks24h.toLocaleString()}
                    sub={fleet.uplinksLastHour > 0 ? `+${fleet.uplinksLastHour} last hr` : 'idle'}
                    subKind={fleet.uplinksLastHour > 0 ? 'up' : undefined}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="GPS LOCK RATE"
                    value={lockRate}
                    unit={fleet.gpsLockRatePct !== null ? '%' : undefined}
                    sub={fleet.noFixCount > 0 ? `${fleet.noFixCount} no-fix packets` : 'all fixes valid'}
                    subKind={fleet.noFixCount > 0 ? 'down' : undefined}
                    accent={lockAccent}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="MEDIAN RSSI"
                    value={fleet.medianRssi !== null ? Math.round(fleet.medianRssi).toString() : '—'}
                    unit={fleet.medianRssi !== null ? 'dBm' : undefined}
                    sub={
                        fleet.medianRssi === null ? 'no rssi data'
                        : fleet.medianRssi > -90 ? 'signal nominal'
                        : fleet.medianRssi > -110 ? 'signal weak'
                        : 'signal critical'
                    }
                    accent={fleet.medianRssi !== null && fleet.medianRssi < -110 ? 'alert' : undefined}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="MISSION TIME"
                    value={missionTime}
                    unit={missionTimeMs !== null ? 'h:m' : undefined}
                    sub={fleet.firstFixT ? 'since first fix' : 'awaiting first fix'}
                />
            </KpiCell>
            <KpiCell>
                <KPI
                    label="ALERTS"
                    value={alerts.length.toString()}
                    sub={alerts.length === 0 ? 'all green' : `${warnCount} warn / ${infoCount} info`}
                    accent={warnCount > 0 ? 'alert' : undefined}
                />
            </KpiCell>
        </div>
    );
}

function KpiCell({ children }: { children: React.ReactNode }) {
    return <div style={{ background: 'var(--sl-bg-1)', borderRight: '1px solid var(--sl-border)' }}>{children}</div>;
}

/* ──────────────────────────────────────────────────────────────
 * Fleet roster (left rail)
 * ────────────────────────────────────────────────────────────── */
function FleetRoster({ devices, selectedId, rowsForSelected, latest, onSelect, now }: {
    devices: DeviceSummary[];
    selectedId: string | null;
    rowsForSelected: TelemetryRow[];
    latest: TelemetryRow | null;
    onSelect: (id: string) => void;
    now: number;
}) {
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10 }}>FLEET</div>
            {devices.length === 0 ? (
                <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    No devices registered. Visit /claim to register your first balloon.
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {devices.map(d => {
                        const isSelected = d.id === selectedId;
                        const fresh = staleness(d.lastContactT, now);
                        const status = d.lastContactT === null ? 'OFFLINE'
                            : d.latestFix !== null ? 'TRACKING'
                            : 'NO GPS';
                        const battSource = isSelected ? latest?.batt : null;
                        const altSource  = isSelected ? latest?.alt  : (d.latestFix?.alt ?? null);
                        return (
                            <button
                                key={d.id}
                                type="button"
                                className={'sl-dev-card' + (isSelected ? ' selected' : '')}
                                onClick={() => onSelect(d.id)}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                    <span style={{ fontWeight: 500, fontFamily: 'var(--sl-mono)' }}>
                                        {d.callsign ?? d.id}
                                    </span>
                                    <span className={
                                        'sl-pill ' + (status === 'TRACKING' ? 'teal' : status === 'NO GPS' ? 'amber' : 'dim')
                                    }>
                                        {status}
                                    </span>
                                </div>
                                <KV k="alt"  v={altSource !== null && altSource !== undefined ? `${altSource.toFixed(0)}` : '—'}
                                    u={altSource !== null && altSource !== undefined ? 'm' : undefined} />
                                <KV k="batt" v={battSource !== null && battSource !== undefined ? battSource.toFixed(2) : '—'}
                                    u={battSource !== null && battSource !== undefined ? 'V' : undefined}
                                    accent={battSource !== null && battSource !== undefined && battSource < 3.5 ? 'amber' : 'teal'} />
                                <KV k="last" v={
                                    d.lastContactT === null
                                        ? '—'
                                        : <Age t={d.lastContactT} now={now} dot={false} />
                                } />
                                {isSelected && rowsForSelected.length > 0 && (
                                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px dashed var(--sl-border)', display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ fontSize: 10, color: 'var(--sl-text-dim2)' }}>{rowsForSelected.length} pkts · </span>
                                        <span className="sl-status-dot" style={{ background: fresh.color }} />
                                        <span style={{ fontSize: 9, color: 'var(--sl-text-dim2)', letterSpacing: '0.10em' }}>{fresh.name}</span>
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function SystemStatus({ status, latest, fleet, lastFetchedAt }: {
    status: 'connecting' | 'connected' | 'disconnected' | 'error';
    latest: TelemetryRow | null;
    fleet: FleetMetrics;
    lastFetchedAt: number | null;
}) {
    const dbState =
        status === 'connected' ? { label: 'CONNECTED', accent: 'teal' as const }
        : status === 'connecting' ? { label: 'CONNECTING', accent: 'dim' as const }
        : status === 'disconnected' ? { label: 'NOT CONFIGURED', accent: 'amber' as const }
        : { label: 'ERROR', accent: 'amber' as const };
    /* Packet rate: uplinks per minute over the last hour. */
    const rate = fleet.uplinksLastHour > 0 ? (fleet.uplinksLastHour / 60).toFixed(2) : null;
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10 }}>SYSTEM STATUS</div>
            <KV k="database" v={dbState.label} accent={dbState.accent} />
            <KV k="last update" v={fmt.time(latest?.t ?? null)} />
            <KV k="poll cycle" v={lastFetchedAt ? `${Math.max(0, Math.floor((Date.now() - lastFetchedAt) / 1000))}s` : '—'} />
            <KV k="packet rate" v={rate ?? '—'} u={rate ? '/min' : undefined} />
            <KV k="uplinks 24h" v={fleet.uplinks24h.toLocaleString()} />
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Center map
 * ────────────────────────────────────────────────────────────── */
function CenterMap({ devices, rows, latest, lastFixRow, selectedDevice, now }: {
    devices: DeviceSummary[];
    rows: TelemetryRow[];
    latest: TelemetryRow | null;
    lastFixRow: TelemetryRow | null;
    selectedDevice: DeviceSummary | null;
    now: number;
}) {
    const balloons: V2Balloon[] = useMemo(() => devices
        .filter(d => d.latestFix !== null)
        .map(d => ({
            id: d.id,
            lat: d.latestFix!.lat,
            lon: d.latestFix!.lon,
            altitude_m: d.latestFix!.alt,
        })),
        [devices]);

    /* Selected device's full track for the trail layer. */
    const flightPath: V2FlightPoint[] = useMemo(() => rows
        .filter(r => r.lat !== null && r.lon !== null)
        .map(r => ({ lat: r.lat as number, lon: r.lon as number, t: r.t })),
        [rows]);

    /* Gateways that received the most recent uplink. Only those with
     * published locations make it onto the map; the rest still render
     * in the GatewaysPanel. */
    const mapGateways: V2Gateway[] = useMemo(() => {
        const list = latest?.gateways ?? [];
        return list
            .filter(g => g.lat !== null && g.lon !== null)
            .map(g => ({
                gateway_id: g.gateway_id,
                lat: g.lat as number,
                lon: g.lon as number,
                rssi: g.rssi,
                snr: g.snr,
            }));
    }, [latest]);

    return (
        <div style={{ position: 'absolute', inset: 0, minWidth: 0 }}>
            <V2MissionMap
                balloons={balloons}
                activeId={selectedDevice?.id ?? null}
                flightPath={flightPath}
                playbackT={null}
                projection="globe"
                gateways={mapGateways}
            />
            <div style={{ position: 'absolute', top: 14, left: 14, display: 'flex', gap: 6, zIndex: 1 }}>
                <span className="sl-pill dim">MAPBOX · DARK</span>
                {lastFixRow && (
                    <span className="sl-pill dim">
                        {(lastFixRow.lat as number).toFixed(2)}° N · {Math.abs(lastFixRow.lon as number).toFixed(2)}° W
                    </span>
                )}
                {latest?.sats !== null && latest?.sats !== undefined && latest.sats > 0 && (
                    <span className="sl-pill teal">FIX VALID · {latest.sats} SAT</span>
                )}
                {(latest?.sats === null || latest?.sats === undefined || latest.sats === 0) && (
                    <span className="sl-pill amber">NO GPS FIX</span>
                )}
            </div>
            <div style={{
                position: 'absolute', bottom: 14, left: 14,
                fontSize: 10, color: 'var(--sl-text-dim3)', letterSpacing: '0.08em',
                zIndex: 1,
            }}>
                STRATOLINK · UPDATED {fmt.time(latest?.t ?? null)}
            </div>
            <div style={{ position: 'absolute', top: 14, right: 14, zIndex: 1 }}>
                <Age t={latest?.t ?? null} now={now} dot prefix="uplink" />
            </div>
            <GatewayCoverageLegend />
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Right rail panels
 * ────────────────────────────────────────────────────────────── */
function SelectedDevicePanel({ device, deviceInfo, latest, lastFixRow, rowCount, now }: {
    device: DeviceSummary;
    deviceInfo: { firmware: string | null } | null;
    latest: TelemetryRow | null;
    lastFixRow: TelemetryRow | null;
    rowCount: number;
    now: number;
}) {
    const altFt = latest?.alt !== null && latest?.alt !== undefined ? Math.round(latest.alt * 3.281) : null;
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10 }}>SELECTED DEVICE</div>
            <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--sl-ok)', marginBottom: 4, fontFamily: 'var(--sl-mono)' }}>
                {device.callsign ?? device.id}
            </div>
            <div className="sl-label-sm" style={{ marginBottom: 12 }}>
                {device.callsign ? device.id : '—'} ·
                {' '}{deviceInfo?.firmware ?? '— firmware'} ·
                {' '}{device.launchedAt ? `launched ${fmt.datetime(device.launchedAt)}` : 'not launched'}
            </div>
            <KV k="position" v={
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Age t={lastFixRow?.t ?? null} now={now} dot />
                    <span>{fmt.lat(lastFixRow?.lat)} {fmt.lon(lastFixRow?.lon)}</span>
                </span>
            } />
            <KV k="alt (gps)" v={
                latest?.alt !== null && latest?.alt !== undefined
                    ? <span>{latest.alt.toFixed(0)} m {altFt !== null && <span style={{ color: 'var(--sl-text-dim3)', fontSize: 10 }}>/ {altFt} ft</span>}</span>
                    : '—'
            } accent={latest?.alt !== null && latest?.alt !== undefined ? 'teal' : 'dim'} />
            {/* Pressure-derived altitude (USSA-1976 ISA) sits directly under
              * the GPS altitude so the operator can compare them at a glance.
              * When GPS is stuck on a stale cached fix the two will diverge —
              * trust the pressure-derived value in that case (the MS5611 is
              * read fresh every uplink). */}
            <KV k="alt (pres)" v={fmtAltitudeM(latest?.presAlt ?? null)}
                accent={latest?.presAlt !== null && latest?.presAlt !== undefined ? 'teal' : 'dim'} />
            <KV k="heading"    v={fmt.num(latest?.hdg, 1)} u={latest?.hdg !== null && latest?.hdg !== undefined ? '°' : undefined} />
            <KV k="ground spd" v={fmt.num(latest?.spd, 2)} u={latest?.spd !== null && latest?.spd !== undefined ? 'm/s' : undefined} />
            <KV k="uptime"     v={latest?.uptime_s !== null && latest?.uptime_s !== undefined ? fmt.duration(latest.uptime_s * 1000) : '—'} />
            <KV k="tx count"   v={latest?.tx_count !== null && latest?.tx_count !== undefined ? latest.tx_count.toLocaleString() : '—'} />
            <KV k="window" v={`${rowCount} pkts`} u="last 24h" />
        </div>
    );
}

function DataFreshnessPanel({ freshness, now }: { freshness: SubsystemFreshness; now: number }) {
    const items: Array<[string, number | null]> = [
        ['last uplink', freshness.packet],
        ['position',    freshness.position],
        ['altitude',    freshness.altitude],
        ['velocity',    freshness.velocity],
        ['battery',     freshness.battery],
        ['solar',       freshness.solar],
        ['temperature', freshness.temperature],
        ['pressure',    freshness.pressure],
        ['lux / uv',    freshness.lux],
        ['rssi / snr',  freshness.rssi],
        ['imu',         freshness.imu],
    ];
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10 }}>DATA FRESHNESS</div>
            <div style={{ fontSize: 11, color: 'var(--sl-text-dim2)', marginBottom: 10, lineHeight: 1.4 }}>
                Time since each subsystem last reported a real value. GPS only refreshes when a fix is held.
            </div>
            {items.map(([label, t]) => (
                <div key={label} style={{ display: 'grid', gridTemplateColumns: '90px 1fr auto', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                    <span style={{ color: 'var(--sl-text-dim)', fontSize: 11 }}>{label}</span>
                    <FreshnessBar t={t} now={now} width={120} />
                    <span style={{ minWidth: 70, textAlign: 'right' }}>
                        <Age t={t} now={now} compact dot={false} />
                    </span>
                </div>
            ))}
        </div>
    );
}

function LiveMetricsPanel({ rows, latest }: { rows: TelemetryRow[]; latest: TelemetryRow | null }) {
    const last = (n: number, getY: (r: TelemetryRow) => number | null) =>
        rows.slice(-n).map(getY);
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10 }}>LIVE METRICS</div>
            <MetricRow name="battery" series={last(20, r => r.batt)}
                value={latest?.batt !== null && latest?.batt !== undefined ? `${latest.batt.toFixed(2)}V` : '—'} />
            <MetricRow name="solar" series={last(20, r => r.sol)}
                value={latest?.sol !== null && latest?.sol !== undefined ? `${latest.sol.toFixed(2)}V` : '—'} />
            <MetricRow name="temp" series={last(20, r => r.temp)}
                value={latest?.temp !== null && latest?.temp !== undefined ? `${latest.temp.toFixed(1)}°C` : '—'} />
            <MetricRow name="lux" series={last(30, r => r.lux)} color="var(--sl-neutral)"
                value={latest?.lux !== null && latest?.lux !== undefined ? `${latest.lux.toLocaleString()}` : '—'} />
            <MetricRow name="rssi" series={last(20, r => r.rssi)}
                value={latest?.rssi !== null && latest?.rssi !== undefined ? `${latest.rssi}dBm` : '—'} />
            <MetricRow name="snr" series={last(20, r => r.snr)}
                value={latest?.snr !== null && latest?.snr !== undefined ? `${latest.snr.toFixed(1)}dB` : '—'} />
            <MetricRow name="pressure" series={last(20, r => r.pres)} color="var(--sl-neutral)"
                value={fmtPressure(latest?.pres ?? null)} />
            {/* Pressure-derived altitude lives next to its source. The barometer
              * stays accurate when GPS drops out (see firmware NOGPS sentinel),
              * so this is the more reliable altitude reading in flight. */}
            <MetricRow name="pres alt" series={last(20, r => r.presAlt)} color="var(--sl-ok)"
                value={fmtAltitudeM(latest?.presAlt ?? null)} />
        </div>
    );
}

function MetricRow({ name, series, value, color = 'var(--sl-ok-mute)' }: {
    name: string;
    series: Array<number | null>;
    value: string;
    color?: string;
}) {
    return (
        <div className="sl-metric-row">
            <span className="name">{name}</span>
            <Sparkline data={series} width={140} height={20} color={color} />
            <span className="val">{value}</span>
        </div>
    );
}

/* GatewaysPanel — list of TTN gateways that received the most recent uplink,
 * sorted strongest-first by RSSI. Multi-gateway reception is the lifeblood of
 * a pico-balloon mission: at altitude a single packet typically lands on
 * 5–30 gateways, and the spread is what enables triangulation when GPS is
 * stale. We deliberately render the count big so a glance answers "is the
 * balloon still being heard widely?" before any RSSI numbers. */
function GatewaysPanel({ latest }: { latest: TelemetryRow | null }) {
    const gateways = latest?.gateways ?? null;
    const count = gateways?.length ?? 0;

    if (!gateways || count === 0) {
        return (
            <div>
                <div className="sl-label-xs" style={{ marginBottom: 10 }}>GATEWAYS</div>
                <div style={{ padding: 12, border: '1px solid var(--sl-border)', fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    Awaiting first uplink with rx_metadata.
                </div>
            </div>
        );
    }

    /* Cap at 8 — the number of gateways above 8 is rarely actionable on a
     * dashboard and the panel needs to leave room for alerts below. The full
     * list always lives in `latest.gateways` for tooling/queries. */
    const top = gateways.slice(0, 8);
    const overflow = count - top.length;

    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span>GATEWAYS · {count}</span>
                {gateways[0]?.rssi !== null && gateways[0]?.rssi !== undefined && (
                    <span style={{ color: 'var(--sl-text-dim2)', fontWeight: 400 }}>
                        BEST {Math.round(gateways[0].rssi)}dBm
                    </span>
                )}
            </div>
            <div style={{ border: '1px solid var(--sl-border)' }}>
                {top.map((g, i) => {
                    /* gateway_id strings can get long (e.g., "eui-323456abcdef0123").
                     * Show the most useful tail end so multiple co-located gateways
                     * are still distinguishable. */
                    const display = g.gateway_id.length > 22
                        ? `…${g.gateway_id.slice(-18)}`
                        : g.gateway_id;
                    return (
                        <div key={`${g.gateway_id}-${i}`} className="sl-metric-row" style={{ borderBottom: i === top.length - 1 && overflow === 0 ? 'none' : '1px solid var(--sl-border)' }}>
                            <span className="name" style={{ fontFamily: 'var(--sl-mono, monospace)', fontSize: 10 }}>
                                {display}
                            </span>
                            <span style={{ color: 'var(--sl-text-dim2)', fontSize: 10, fontVariantNumeric: 'tabular-nums' }}>
                                {g.snr !== null ? `${g.snr.toFixed(1)}dB` : ''}
                            </span>
                            <span className="val" style={{ fontVariantNumeric: 'tabular-nums' }}>
                                {g.rssi !== null ? `${Math.round(g.rssi)}dBm` : '—'}
                            </span>
                        </div>
                    );
                })}
                {overflow > 0 && (
                    <div className="sl-metric-row" style={{ borderTop: '1px solid var(--sl-border)' }}>
                        <span className="name" style={{ color: 'var(--sl-text-dim2)' }}>
                            +{overflow} more
                        </span>
                        <span></span>
                        <span></span>
                    </div>
                )}
            </div>
        </div>
    );
}

function AlertsPanel({ alerts, now }: { alerts: FleetAlert[]; now: number }) {
    if (alerts.length === 0) {
        return (
            <div>
                <div className="sl-label-xs" style={{ marginBottom: 8 }}>ALERTS · 0</div>
                <div style={{ padding: 12, border: '1px solid var(--sl-border)', fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    All systems nominal.
                </div>
            </div>
        );
    }
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 8 }}>ALERTS · {alerts.length}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {alerts.map(a => (
                    <div
                        key={a.id}
                        style={{
                            padding: 12,
                            border: '1px solid var(--sl-border)',
                            background: a.severity === 'warn' ? 'var(--sl-alert-soft)' : undefined,
                            fontSize: 11,
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{
                                color: a.severity === 'warn' ? 'var(--sl-alert)' : 'var(--sl-ok)',
                                letterSpacing: '0.10em',
                                textTransform: 'uppercase',
                                fontSize: 10,
                                fontWeight: 500,
                            }}>
                                {a.severity === 'warn' ? 'WARN' : 'INFO'} · {a.title}
                            </span>
                            <span style={{ color: 'var(--sl-text-dim3)', fontFamily: 'var(--sl-mono)' }}>
                                {fmt.time(a.t)}
                            </span>
                        </div>
                        <div style={{ color: 'var(--sl-text-dim)' }}>{a.detail}</div>
                        <div style={{ marginTop: 6 }}>
                            <Age t={a.t} now={now} compact dot={false} />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function CadencePanel({ rows, now }: { rows: TelemetryRow[]; now: number }) {
    const { ref, width } = useElementSize(280, 28);
    const tEnd = rows.length ? rows[rows.length - 1].t : now;
    const tStart = tEnd - 2 * 3600 * 1000;
    return (
        <div>
            <div className="sl-label-xs" style={{ marginBottom: 8 }}>PACKET CADENCE · 2h</div>
            <div ref={ref} style={{ width: '100%' }}>
                <CadenceStrip data={rows} t0={tStart} t1={tEnd} width={width} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--sl-text-dim3)', marginTop: 4 }}>
                <span>-2h</span><span>-1h</span><span>now</span>
            </div>
        </div>
    );
}
