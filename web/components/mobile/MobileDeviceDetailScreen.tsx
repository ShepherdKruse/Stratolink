'use client';

import { SectionLabel, SlHeader, StackedLineChart } from './mobileStratolinkUi';
import {
    deviceUiStatus,
    fmtCoords,
    formatAge,
    pillClass,
    type MobileFleetDeviceRow,
} from './mobileStratolinkUtils';
import MobilePositionPreviewMap from './MobilePositionPreviewMap';

type TelemetryPoint = Record<string, unknown>;

function chartRows(rows: TelemetryPoint[]): Array<Record<string, number | null | undefined> & { t: number }> {
    const out: Array<Record<string, number | null | undefined> & { t: number }> = [];
    for (const r of rows) {
        const t = new Date(String(r.time)).getTime();
        if (Number.isNaN(t)) continue;
        out.push({
            t,
            alt: coerceNum(r.altitude_m),
            batt: coerceNum(r.battery_voltage),
            sol: coerceNum(r.solar_voltage),
            temp: coerceNum(r.temperature),
            lux: coerceNum(r.ambient_lux),
            rssi: coerceNum(r.rssi),
            sats: coerceNum(r.gps_satellites),
        });
    }
    return out.sort((a, b) => a.t - b.t);
}

function coerceNum(v: unknown): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

interface MobileDeviceDetailScreenProps {
    device: MobileFleetDeviceRow;
    telemetryRows: TelemetryPoint[];
    flightPathData?: Array<{ lat: number; lon: number; time: Date }>;
    onBack: () => void;
    onOpenFullMap: () => void;
}

export default function MobileDeviceDetailScreen({
    device,
    telemetryRows,
    flightPathData = [],
    onBack,
    onOpenFullMap,
}: MobileDeviceDetailScreenProps) {
    const charts = chartRows(telemetryRows);
    const last = charts.length > 0 ? charts[charts.length - 1] : null;
    const batt = coerceNum(last?.batt) ?? coerceNum(device.battery_voltage);
    const alt = coerceNum(last?.alt) ?? (device.awaiting_gps ? null : device.altitude_m);
    const temp = coerceNum(last?.temp);
    const solar = coerceNum(last?.sol);
    const rssiRecent = coerceNum(last?.rssi) ?? coerceNum(device.rssi);
    const sats = coerceNum(last?.sats) ?? coerceNum(device.gps_satellites);
    const status = deviceUiStatus(device);
    const gpsHighlight = typeof sats === 'number' && sats > 0;

    return (
        <div className="flex h-full flex-col overflow-hidden bg-[var(--bg)] text-[var(--text)] pb-[calc(88px+env(safe-area-inset-bottom))]">
            <SlHeader
                back
                onBack={onBack}
                sub="DEVICE"
                title={device.id}
                right={<span className={pillClass(status)}>{status}</span>}
            />

            <div className="min-h-0 flex-1 overflow-y-auto">
                <div
                    className="grid shrink-0 grid-cols-2"
                    style={{ borderBottom: '1px solid var(--border)', fontFamily: 'var(--sans)' }}>
                    <div style={{ padding: '20px 18px', borderRight: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 8 }}>
                            Altitude
                        </div>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1 }}>
                            {device.awaiting_gps ? '—' : Number.isFinite(alt) ? Math.round(Number(alt)) : '—'}
                            <span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>m</span>
                        </div>
                        <div className="mt-2 font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            contact {formatAge(device.last_contact)} ago
                        </div>
                    </div>
                    <div style={{ padding: '20px 18px', borderBottom: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 8 }}>
                            Battery
                        </div>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1 }}>
                            {batt != null ? batt.toFixed(2) : '—'}
                            <span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>V</span>
                        </div>
                        <div className="mt-2 font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            from last row
                        </div>
                    </div>
                    <div style={{ padding: '20px 18px', borderRight: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 8 }}>
                            Signal
                        </div>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1 }}>
                            {rssiRecent != null ? Math.round(rssiRecent) : '—'}
                            <span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>dBm</span>
                        </div>
                        <div className="mt-2 font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            uplink cadence varies
                        </div>
                    </div>
                    <div style={{ padding: '20px 18px' }}>
                        <div style={{ fontSize: 9, letterSpacing: '0.14em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 8 }}>
                            GPS Satellites
                        </div>
                        <div
                            style={{
                                fontFamily: 'var(--mono)',
                                fontSize: 26,
                                fontWeight: 500,
                                lineHeight: 1,
                                color: gpsHighlight ? 'var(--text-hi)' : 'var(--alert)',
                            }}>
                            {sats != null ? Math.round(sats) : '—'}
                            <span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>/ 24</span>
                        </div>
                        <div className="mt-2 font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            {device.awaiting_gps ? 'Awaiting fix' : 'GPS ok'}
                        </div>
                    </div>
                </div>

                <SectionLabel right={
                    <button type="button" onClick={onOpenFullMap} className="bg-transparent uppercase" style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--ok)', letterSpacing: '0.08em', fontWeight: 500 }}>
                        Open full map →
                    </button>
                }>
                    Position
                </SectionLabel>

                <div className="relative overflow-hidden border-b border-t bg-[var(--bg)]" style={{ borderColor: 'var(--border)' }}>
                    <MobilePositionPreviewMap lat={device.lat} lon={device.lon} flightPathData={flightPathData} />
                    <div
                        className="pointer-events-none absolute bottom-3 left-4 font-mono text-[11px] text-[var(--text-hi)]"
                        style={{ textShadow: '0 0 4px rgba(0,0,0,0.8)', fontVariantNumeric: 'tabular-nums' }}>
                        {fmtCoords(device.lat, device.lon)}
                    </div>
                </div>

                <SectionLabel right={<span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim2)' }}>{charts.length ? `${charts.length} pts` : '—'}</span>}>
                    Telemetry
                </SectionLabel>

                <StackedLineChart
                    title="Battery"
                    valueDisplay={batt != null ? batt.toFixed(2) : '—'}
                    unitSuffix=" V"
                    data={charts}
                    getY={(r) => coerceNum(r.batt)}
                    min={3.2}
                    max={5.6}
                />
                <StackedLineChart
                    title="Altitude"
                    valueDisplay={alt != null && Number.isFinite(alt) ? Math.round(alt) : '—'}
                    unitSuffix=" m"
                    data={charts}
                    getY={(r) => coerceNum(r.alt)}
                />
                <StackedLineChart
                    title="Solar"
                    valueDisplay={solar != null ? solar.toFixed(2) : '—'}
                    unitSuffix=" V"
                    data={charts}
                    getY={(r) => coerceNum(r.sol)}
                    min={0}
                    max={6}
                />
                <StackedLineChart title="Temperature" valueDisplay={temp != null ? temp.toFixed(1) : '—'} unitSuffix=" °C" data={charts} getY={(r) => coerceNum(r.temp)} />

                <SectionLabel>Data freshness</SectionLabel>
                <div className="px-5 pb-28">
                    {[
                        ['Last contact', device.last_contact],
                        ['Fleet row', telemetryRows.at(-1) ? String((telemetryRows.at(-1) as TelemetryPoint).time) : undefined],
                    ].map(([label, iso]) => (
                        <div key={label} className="sl-kv-row">
                            <span className="k">{label}</span>
                            <span className="v">{formatAge(iso ?? null)} ago</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}