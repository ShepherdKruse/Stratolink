import { useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faArrowUp,
    faBolt,
    faCircle,
    faClockRotateLeft,
    faMoon,
    faSolarPanel,
    faSun,
} from '@fortawesome/free-solid-svg-icons';
import { fmt, type TelemetryRow } from '@/components/dashboard-v2/atoms';
import type { DeviceSummary } from '@/components/dashboard-v2/useTelemetry';
import {
    buildFlightSeries,
    computePayloadAttitude,
} from '@/lib/telemetry/flightSeries';
import { relTime, stamp, tlmFmt, type StatusLevel } from '@/lib/telemetry/telemetryV3Format';
import { useGatewayPoints } from '@/lib/gateways/data';
import { haversineKm } from '@/lib/gateways/range';
import { LineTrend } from './charts';
import { Divider, DOT, Group } from './primitives';
import { OfficialBadge, BalloonOwner } from '../BalloonIdentity';
import { balloonName } from '@/lib/telemetry/fleetPlayback';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "May 17, 2026 · 15:55 UTC" — no seconds, friendlier than the raw stamp. */
function fmtLaunchDate(ms: number): string {
    const d = new Date(ms);
    return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

function fmtLaunchTime(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

function fmtLaunch(ms: number): string {
    return `${fmtLaunchDate(ms)} - ${fmtLaunchTime(ms)}`;
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
    /** Recorded data that must not be presented as an active transmission. */
    recordedHistory?: boolean;
    /** Controls which slices of the panel render. 'full' (default, desktop)
     *  shows everything. On mobile the panel is split: 'summary' is the
     *  always-visible top block (brand, device, top-level metrics, link
     *  status) and 'charts' is the pull-up drawer (chart sections + footer,
     *  no header). */
    variant?: 'full' | 'summary' | 'charts';
    /** When set, clicking a time-series chart scrubs to that time. */
    onPickTime?: (t: number) => void;
};

/** Live-updating "time since last contact", value only (for a key metric). */
function LastContactValue({ lastContactT }: { lastContactT: number | null }) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 3000);
        return () => clearInterval(id);
    }, []);
    if (lastContactT == null) return <>-</>;
    return <>{relTime(Math.max(0, now - lastContactT))}</>;
}

/** Header status — a quiet dot + label, not a button/chip. */
function HeaderStatus({ status, label, icon = faCircle }: { status: StatusLevel; label: string; icon?: typeof faCircle }) {
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <FontAwesomeIcon icon={icon} style={{ width: icon === faCircle ? 6 : 10, height: icon === faCircle ? 6 : 10, color: DOT[status], flexShrink: 0 }} aria-hidden />
            <span className="eyebrow" style={{ color: 'var(--t-text-2)', fontSize: 9.5 }}>{label}</span>
        </span>
    );
}

/** Show the archived sample time or connection status at the chart cursor. */
function ConnectionStatus({ connected, archived, recordedAt }: { connected: boolean; archived: boolean; recordedAt: number | null }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <HeaderStatus
                status={connected ? 'nominal' : 'critical'}
                label={connected ? archived ? 'Recorded telemetry' : 'Transmitting' : 'No connection'}
                icon={connected && archived ? faClockRotateLeft : faCircle}
            />
            {connected && archived && recordedAt != null && (
                <time dateTime={new Date(recordedAt).toISOString()} className="mono" style={{ color: 'var(--t-text-3)', fontSize: 9.5 }}>
                    {fmtLaunch(recordedAt)}
                </time>
            )}
        </div>
    );
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

/** Sun (warming with brightness) by day, moon at night — relates lux to phase. */
function DaylightIcon({ lux }: { lux: number }) {
    if (lux < 10) {
        return (
            <FontAwesomeIcon icon={faMoon} style={{ width: 14, height: 14, color: 'var(--t-text-3)', flexShrink: 0 }} aria-hidden />
        );
    }
    const col = lux < 200 ? '#5C6B7A' : lux < 5000 ? '#9A7B3C' : lux < 25000 ? '#C9922E' : '#E8B020';
    return (
        <FontAwesomeIcon icon={faSun} style={{ width: 14, height: 14, color: col, flexShrink: 0 }} aria-hidden />
    );
}

/** Small solar-panel glyph — amber when the array is generating. */
function SolarIcon({ color }: { color: string }) {
    return (
        <FontAwesomeIcon icon={faSolarPanel} style={{ width: 15, height: 13, color, flexShrink: 0 }} aria-hidden />
    );
}

/** Tiny payload-tilt indicator: a mast leaning from vertical by `deg`. */
function TiltIcon({ deg, color }: { deg: number; color: string }) {
    const d = Math.max(-80, Math.min(80, deg));
    return (
        <FontAwesomeIcon icon={faArrowUp} style={{ width: 14, height: 14, color, flexShrink: 0, transform: `rotate(${d}deg)`, transformOrigin: 'center bottom' }} aria-hidden />
    );
}

export default function TelemetryV3Panel({ device, devices, onSelect, scrubRow, summary, rows, isFuture = false, recordedHistory = false, variant = 'full', onPickTime }: TelemetryV3PanelProps) {
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
    const lux = row?.lux ?? null;
    const rssi = row?.rssi;
    const snr = row?.snr;
    const gwNow = row?.gateways?.length ?? null;

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

    /* No usable series yet (brand-new or pre-launch device). The HEADER must
     * still render — it holds the balloon selector, and replacing the whole
     * panel stranded users on a data-less device with no way to switch. Only
     * the chart body gives way to the note. */
    const awaiting = rows.length < 2;
    const archived = recordedHistory || ['landed', 'recovered', 'retired', 'lost'].includes(device?.status?.toLowerCase() ?? '');
    const registryStillFlying = recordedHistory && device?.status?.toLowerCase() === 'flying';
    const launchLine = registryStillFlying && rows.length
        ? { text: `Records from ${fmtLaunchDate(rows[0].t)}`, time: rows[0].t }
        : device?.launchedAt
            ? { text: `Launched ${rows[0]?.locationApproximate ? 'from San Francisco - ' : ''}${fmtLaunchDate(device.launchedAt)}`, time: device.launchedAt }
            : { text: 'Awaiting launch', time: null };

    return (
        <>
            {showHeader && (
            <div style={{ borderBottom: compact ? undefined : '1px solid var(--t-border)', flexShrink: 0 }}>
                <h1 className="dashboard-device-title">{device ? balloonName(device) : 'Balloon'} <OfficialBadge official={device?.official} /></h1>
                {device?.ownerGithub && <div className="detail-owner"><BalloonOwner device={device} /></div>}
                <div style={{ padding: compact ? '8px var(--telemetry-gutter, 18px) 0' : '12px var(--telemetry-gutter, 18px) 0' }}>
                    {/* One line: when it doesn't fit, the time wraps onto a clipped second line, then the date ellipsizes. */}
                    <div className="detail-status-line">
                        <span className="detail-status-main">
                            {device?.status && (
                                <>
                                    <HeaderStatus status="nominal" label={registryStillFlying ? 'Missing' : String(device.status)} />
                                    <span style={{ color: 'var(--t-text-4)', fontSize: 10 }}>-</span>
                                </>
                            )}
                            <span className="mono detail-status-text">
                                {launchLine.text}
                            </span>
                        </span>
                        {launchLine.time != null && <span className="mono detail-status-time">{` - ${fmtLaunchTime(launchLine.time)}`}</span>}
                    </div>
                </div>
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(72px, 1fr))',
                        gap: compact ? '10px 18px' : '16px 18px',
                        padding: compact ? '11px var(--telemetry-gutter, 18px) 10px' : '16px var(--telemetry-gutter, 18px) 12px',
                    }}
                >
                    <Metric label="Flight time" value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '-'} />
                    <Metric label="Total dist" value={Math.round(summary.distanceKm).toLocaleString('en-US')} unit="km" />
                    <Metric label="Last contact" value={<LastContactValue lastContactT={device?.lastContactT ?? null} />} />
                </div>
                <div style={{ padding: compact ? '0 var(--telemetry-gutter, 18px) 12px' : '0 var(--telemetry-gutter, 18px) 16px' }}>
                    <ConnectionStatus connected={!isFuture && !awaiting} archived={archived} recordedAt={scrubRow?.t ?? null} />
                </div>
            </div>
            )}

            {awaiting && (
                <div style={{ padding: '24px var(--telemetry-gutter, 18px)', color: 'var(--t-text-3)', fontSize: 12 }} className="mono">
                    Awaiting telemetry packets...
                </div>
            )}

            {showBody && !awaiting && (
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
                                {altVal != null ? tlmFmt.int(altVal) : '-'}
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
                        onPickTime={onPickTime}
                    />
                </div>
                <Divider />
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            Temperature
                        </span>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                            {row?.temp != null ? tlmFmt.d1(row.temp) : '-'}
                            {row?.temp != null && <span className="mono" style={{ fontSize: 11, fontWeight: 500, color: 'var(--t-text-3)', marginLeft: 3 }}>°C</span>}
                        </span>
                    </div>
                    <LineTrend series={flight.temp} times={flight.times} status="nominal" fmtFn={(v) => tlmFmt.d1(v)} unit="°C" height={44} scrubT={scrubRow?.t ?? null} onPickTime={onPickTime} />
                </div>
            </Group>

            <Group
                index="02"
                title="Power & sun"
                gkey="power"
            >
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0 10px', padding: '14px 0' }}>
                    <Metric
                        label="Storage"
                        value={batt != null ? tlmFmt.d2(batt) : '-'}
                        unit={batt != null ? 'V' : undefined}
                        icon={batt != null ? <FontAwesomeIcon icon={faBolt} style={{ width: 11, height: 13, color: 'var(--t-text-3)' }} aria-hidden /> : undefined}
                    />
                    <Metric
                        label="Solar"
                        value={solar != null ? tlmFmt.d2(solar) : '-'}
                        unit={solar != null ? 'V' : undefined}
                        icon={solar != null ? <SolarIcon color={solar >= 1 ? '#C9922E' : 'var(--t-text-3)'} /> : undefined}
                    />
                    <Metric
                        label="Ambient"
                        value={lux != null ? Math.round(lux).toLocaleString('en-US') : '-'}
                        unit={lux != null ? 'lux' : undefined}
                        icon={lux != null ? <DaylightIcon lux={lux} /> : undefined}
                    />
                    <Metric
                        label="Orientation"
                        value={tilt != null ? `${Math.round(tilt)}°` : '-'}
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
                    <Metric label="Gateways" value={gwNow != null ? `${gwNow}` : '-'} unit={gwVisible != null ? `/ ${gwVisible}` : undefined} />
                    <Metric label="GPS sats" value={row?.sats != null ? `${row.sats}` : '-'} />
                    <Metric label="RSSI" value={rssi != null ? tlmFmt.int(rssi) : '-'} unit={rssi != null ? 'dBm' : undefined} />
                    <Metric label="SNR" value={snr != null ? tlmFmt.d1(snr) : '-'} unit={snr != null ? 'dB' : undefined} />
                </div>
            </Group>


            {flight.times.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px var(--telemetry-gutter, 18px) 20px', flexShrink: 0 }}>
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
