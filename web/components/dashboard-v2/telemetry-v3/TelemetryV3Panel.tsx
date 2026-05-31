'use client';

import Image from 'next/image';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fmt, type TelemetryRow } from '@/components/dashboard-v2/atoms';
import { fmtAltitudeM } from '@/components/dashboard-v2/shared';
import type { DeviceSummary } from '@/components/dashboard-v2/useTelemetry';
import {
    altDelta30m,
    ascentRateMpsAtScrub,
    buildFlightSeries,
    computePayloadAttitude,
    last,
    maxGatewaysSeen,
    noFixDurationMs,
} from '@/lib/telemetry/flightSeries';
import { evalStatus, relTime, stamp, tlmFmt, type StatusLevel } from '@/lib/telemetry/telemetryV3Format';
import { LineTrend, PowerOverlay, SignalTrendRow, StateStrip } from './charts';
import {
    AscentRate,
    AttitudeBubble,
    DaylightMeter,
    GpsKvRow,
    HeadingCompass,
    PowerFlow,
    SignalQuality,
    TrendDelta,
} from './extras';
import ThemeToggle from '@/components/dashboard-v2/ThemeToggle';
import { Divider, Group, StatTile, StatusChip } from './primitives';

type FlightSummary = { durationMs: number | null; distanceKm: number };

export type TelemetryV3PanelProps = {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    summary: FlightSummary;
    rows: TelemetryRow[];
};

function LiveContact({ lastContactT }: { lastContactT: number | null }) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 3000);
        return () => clearInterval(id);
    }, []);
    if (lastContactT == null) return <span className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-3)' }}>—</span>;
    return (
        <span className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-2)', fontWeight: 600 }}>
            +{relTime(Math.max(0, now - lastContactT))}
        </span>
    );
}

function TriageBanner({ alerts, onJump }: { alerts: { sev: StatusLevel; key: string; title: string; detail: string }[]; onJump: (k: string) => void }) {
    const [expanded, setExpanded] = useState(false);
    if (alerts.length === 0) return null;
    const lead = alerts[0];
    const rest = alerts.slice(1);
    const leadCol = lead.sev === 'critical' ? 'var(--t-critical)' : lead.sev === 'warn' ? 'var(--t-warn)' : 'var(--t-nominal)';

    return (
        <div style={{ margin: '14px 18px 0', borderRadius: 4, border: '1px solid var(--t-border)', overflow: 'hidden', background: 'var(--t-panel-2)' }}>
            <button
                type="button"
                onClick={() => onJump(lead.key)}
                style={{ width: '100%', display: 'flex', alignItems: 'stretch', gap: 0, background: 'transparent', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left' }}
            >
                <div style={{ width: 4, flexShrink: 0, background: leadCol }} />
                <div style={{ padding: '12px 14px', minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 7 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9 }}>Needs attention</span>
                        <span className="eyebrow" style={{ color: leadCol, fontSize: 9 }}>{lead.sev === 'critical' ? 'Critical' : 'Warning'}</span>
                    </div>
                    <div className="disp" style={{ fontSize: 14, fontWeight: 700, color: 'var(--t-text)' }}>{lead.title}</div>
                    <div className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-2)', marginTop: 2, lineHeight: 1.35 }}>{lead.detail}</div>
                </div>
            </button>
            {rest.length > 0 && (
                <div style={{ borderTop: '1px solid var(--t-border)' }}>
                    <button
                        type="button"
                        onClick={() => setExpanded((v) => !v)}
                        style={{ width: '100%', padding: '8px 14px', background: 'transparent', border: 0, cursor: 'pointer', color: 'var(--t-text-2)' }}
                    >
                        <span className="eyebrow" style={{ fontSize: 9 }}>{rest.length} more</span>
                    </button>
                    {expanded &&
                        rest.map((a) => (
                            <button
                                key={a.key}
                                type="button"
                                onClick={() => onJump(a.key)}
                                style={{ width: '100%', padding: '8px 14px', background: 'transparent', border: 0, borderTop: '1px solid var(--t-hairline)', cursor: 'pointer', textAlign: 'left' }}
                            >
                                <div className="disp" style={{ fontSize: 12, fontWeight: 600 }}>{a.title}</div>
                                <div className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)' }}>{a.detail}</div>
                            </button>
                        ))}
                </div>
            )}
        </div>
    );
}

export default function TelemetryV3Panel({ device, devices, onSelect, scrubRow, summary, rows }: TelemetryV3PanelProps) {
    const [open, setOpen] = useState({ flight: true, power: true, link: true, att: true });
    const toggle = (k: keyof typeof open) => setOpen((o) => ({ ...o, [k]: !o[k] }));

    const flight = useMemo(() => buildFlightSeries(rows), [rows]);
    const gwTotal = useMemo(() => maxGatewaysSeen(flight), [flight]);

    const hasFix = scrubRow?.lat != null && scrubRow.lon != null;
    const sats = scrubRow?.sats ?? 0;
    const gpsStatus: StatusLevel = !hasFix || sats <= 0 ? 'critical' : sats < 4 ? 'warn' : 'nominal';

    const altVal = scrubRow?.presAlt;
    const batt = scrubRow?.batt;
    const solar = scrubRow?.sol;
    const rssi = scrubRow?.rssi;
    const snr = scrubRow?.snr;
    const gwNow = scrubRow?.gateways?.length ?? last(flight.gw) ?? 0;

    const payloadAttitude = useMemo(
        () =>
            scrubRow
                ? computePayloadAttitude(scrubRow.ax, scrubRow.ay, scrubRow.az)
                : null,
        [scrubRow],
    );

    const jumpTo = useCallback((key: string) => {
        const k = key as keyof typeof open;
        setOpen((o) => ({ ...o, [k]: true }));
        requestAnimationFrame(() => {
            const el = document.getElementById(`grp-${key}`);
            const sc = document.querySelector('.tlm-scroll');
            if (el && sc) {
                const top = el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 8;
                sc.scrollTo({ top, behavior: 'smooth' });
            }
        });
    }, []);

    const alerts = useMemo(() => {
        const list: { sev: StatusLevel; key: string; title: string; detail: string }[] = [];
        const noFix = noFixDurationMs(flight);
        if (gpsStatus === 'critical') {
            list.push({
                sev: 'critical',
                key: 'flight',
                title: 'GPS — no fix',
                detail: noFix != null ? `No lock for ${relTime(noFix)} · using barometric altitude` : 'No satellite lock on latest packet',
            });
        }
        if (batt != null && batt < 3.45) {
            list.push({
                sev: batt < 3.2 ? 'critical' : 'warn',
                key: 'power',
                title: 'Battery low',
                detail: `${tlmFmt.d2(batt)} V on last packet`,
            });
        }
        if (rssi != null && rssi < -110) {
            list.push({
                sev: rssi < -118 ? 'critical' : 'warn',
                key: 'link',
                title: 'Signal marginal',
                detail: `${tlmFmt.int(rssi)} dBm · ${gwNow} of ${gwTotal} gateways on last uplink`,
            });
        }
        return list.sort((a, b) => (a.sev === 'critical' ? -1 : b.sev === 'critical' ? 1 : 0));
    }, [flight, gpsStatus, batt, rssi, gwNow, gwTotal]);

    const altDelta = altDelta30m(flight);
    const rate = useMemo(() => ascentRateMpsAtScrub(rows, scrubRow), [rows, scrubRow]);
    const lastFixIdx = [...flight.sats].reverse().findIndex((s) => s != null && s > 0);
    const lastFixT =
        lastFixIdx >= 0 && flight.times.length
            ? stamp(flight.times[flight.times.length - 1 - lastFixIdx])
            : '—';

    const presAltStr = fmtAltitudeM(altVal ?? null).replace(' m', '');
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
            <div style={{ borderBottom: '1px solid var(--t-border)', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '15px 18px 0' }}>
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
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '14px 18px 0' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="eyebrow" style={{ color: 'var(--t-text-3)', marginBottom: 6 }}>
                            Monitoring
                        </div>
                        <select
                            value={device?.id ?? ''}
                            onChange={(e) => onSelect(e.target.value)}
                            className="disp"
                            style={{
                                fontSize: 24,
                                fontWeight: 600,
                                color: 'var(--t-text)',
                                background: 'var(--t-panel)',
                                border: 'none',
                                cursor: 'pointer',
                                padding: 0,
                                maxWidth: '100%',
                            }}
                        >
                            {devices.map((d) => (
                                <option key={d.id} value={d.id}>
                                    {d.callsign ?? d.id}
                                </option>
                            ))}
                        </select>
                        {device?.callsign && (
                            <div className="mono" style={{ fontSize: 10, color: 'var(--t-text-3)', marginTop: 2 }}>
                                {device.id}
                            </div>
                        )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                        <StatusChip status={gpsStatus} label={hasFix ? 'Fix' : 'No fix'} />
                        <StatusChip status="nominal" label={device?.status ? String(device.status) : '—'} />
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px 14px' }}>
                    <span className="mono" style={{ fontSize: 10.5, color: 'var(--t-text-3)' }}>
                        {device?.launchedAt ? `Launched ${fmt.datetime(device.launchedAt)}` : 'Not launched'}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className="live-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--t-nominal)' }} />
                        <span className="eyebrow" style={{ color: 'var(--t-text-3)', fontSize: 9 }}>
                            Last contact
                        </span>
                        <LiveContact lastContactT={device?.lastContactT ?? null} />
                    </span>
                </div>
                <TriageBanner alerts={alerts} onJump={jumpTo} />
                <div style={{ display: 'flex', gap: 6, padding: '14px 18px 16px' }}>
                    <div style={{ flex: 1.4, minWidth: 0, padding: '11px 12px', background: 'var(--t-panel-2)', borderRadius: 3, border: '1px solid var(--t-border)' }}>
                        <div className="eyebrow" style={{ color: 'var(--t-text-3)', marginBottom: 5, fontSize: 9 }}>
                            Alt · pressure
                        </div>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 3 }}>
                            <span className="disp mono" style={{ fontSize: 21, fontWeight: 600, color: 'var(--t-text)', lineHeight: 1 }}>
                                {presAltStr === '—' ? '—' : presAltStr}
                            </span>
                            {presAltStr !== '—' && <span className="mono" style={{ fontSize: 11, color: 'var(--t-text-3)' }}>m</span>}
                        </div>
                        {altDelta != null && (
                            <div style={{ marginTop: 6 }}>
                                <TrendDelta delta={altDelta} unit="m" window="30 min" />
                            </div>
                        )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0, padding: '11px 12px', background: 'var(--t-panel-2)', borderRadius: 3, border: '1px solid var(--t-border)' }}>
                        <StatTile label="Total time" value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '—'} />
                    </div>
                    <div style={{ flex: 1.1, minWidth: 0, padding: '11px 12px', background: 'var(--t-panel-2)', borderRadius: 3, border: '1px solid var(--t-border)' }}>
                        <StatTile label="Total dist" value={`${Math.round(summary.distanceKm)}`} unit="km" />
                    </div>
                </div>
            </div>

            <Group
                index="01"
                title="Flight path"
                gkey="flight"
                statuses={[altStatus, gpsStatus]}
                summary={altVal != null ? `${tlmFmt.int(altVal)} m` : '—'}
                open={open.flight}
                onToggle={() => toggle('flight')}
            >
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            Altitude <span style={{ color: 'var(--t-text-4)', fontSize: 9 }}>m · pres</span>
                        </span>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                            {altVal != null ? tlmFmt.int(altVal) : '—'}
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
                    />
                </div>
                <Divider />
                <div style={{ padding: '15px 0' }}>
                    <HeadingCompass heading={scrubRow?.hdg ?? last(flight.heading) ?? null} speed={scrubRow?.spd != null ? scrubRow.spd * 3.6 : last(flight.speed) ?? null} />
                </div>
                <Divider />
                <AscentRate rate={rate} />
                <Divider />
                <div style={{ padding: '13px 0 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            GPS satellites
                        </span>
                        <StatusChip status={gpsStatus} label={sats > 0 ? `${sats} sats` : 'No fix'} />
                    </div>
                    <StateStrip sats={flight.sats} times={flight.times} />
                    <GpsKvRow noFixMs={noFixDurationMs(flight)} lastFixStamp={lastFixT} />
                </div>
            </Group>

            <Group
                index="02"
                title="Power & sun"
                gkey="power"
                statuses={[evalStatus(batt, { warn: 3.45, crit: 3.2, dir: 'high' }), 'nominal']}
                summary={batt != null ? `${tlmFmt.d2(batt)} V` : '—'}
                open={open.power}
                onToggle={() => toggle('power')}
            >
                <div style={{ padding: '14px 0 4px' }}>
                    <PowerFlow solarV={solar} battV={batt} />
                </div>
                <Divider />
                <div style={{ paddingTop: 6 }}>
                    <PowerOverlay flight={flight} height={104} />
                </div>
                <Divider />
                <div style={{ paddingTop: 14 }}>
                    <DaylightMeter lux={scrubRow?.lux ?? last(flight.lux) ?? null} />
                </div>
            </Group>

            <Group
                index="03"
                title="Link"
                gkey="link"
                statuses={[evalStatus(rssi, { warn: -110, crit: -118, dir: 'high' }), evalStatus(snr, { warn: 5, crit: 0, dir: 'high' })]}
                summary={rssi != null ? `${tlmFmt.int(rssi)} dBm` : '—'}
                open={open.link}
                onToggle={() => toggle('link')}
            >
                <SignalQuality rssi={rssi} snr={snr} gateways={gwNow} gwTotal={gwTotal} />
                <Divider />
                <SignalTrendRow
                    label="Signal strength"
                    unit="RSSI · dBm"
                    value={rssi != null ? tlmFmt.int(rssi) : '—'}
                    series={flight.rssi}
                    target={-110}
                    dir="high"
                    fmtFn={(v) => tlmFmt.int(v)}
                />
                <Divider />
                <SignalTrendRow
                    label="Signal clarity"
                    unit="SNR · dB"
                    value={snr != null ? tlmFmt.d1(snr) : '—'}
                    series={flight.snr}
                    target={5}
                    dir="high"
                    fmtFn={(v) => tlmFmt.d1(v)}
                />
            </Group>

            <Group
                index="04"
                title="Attitude & environment"
                gkey="att"
                statuses={['nominal', 'nominal']}
                summary={scrubRow?.temp != null ? `${tlmFmt.d1(scrubRow.temp)} °C` : '—'}
                open={open.att}
                onToggle={() => toggle('att')}
            >
                <div style={{ padding: '13px 0' }}>
                    <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                        Payload motion
                    </span>
                    <div style={{ marginTop: 10 }}>
                        <AttitudeBubble attitude={payloadAttitude} />
                    </div>
                </div>
                <Divider />
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            External temp
                        </span>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                            {scrubRow?.temp != null ? tlmFmt.d1(scrubRow.temp) : '—'}
                        </span>
                    </div>
                    <LineTrend series={flight.temp} times={flight.times} band={[-60, 20]} status="nominal" fmtFn={(v) => tlmFmt.d1(v)} unit="°C" emphasis="low" height={44} />
                </div>
                <Divider />
                <div style={{ padding: '13px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span className="eyebrow" style={{ color: 'var(--t-text-2)' }}>
                            Pressure
                        </span>
                        <span className="disp mono" style={{ fontSize: 22, fontWeight: 600 }}>
                            {scrubRow?.pres != null ? tlmFmt.d1(scrubRow.pres) : '—'}
                        </span>
                    </div>
                    <LineTrend series={flight.press} times={flight.times} band={[200, 320]} status="nominal" fmtFn={(v) => tlmFmt.d1(v)} unit="hPa" emphasis="low" height={44} />
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
    );
}
