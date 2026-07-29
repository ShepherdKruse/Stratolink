'use client';

import { useMemo, useState } from 'react';
import { telemetryNumber } from '@/lib/telemetry-values';
import { SectionLabel, SlHeader, StackedLineChart } from './mobileStratolinkUi';

type TelemetryPoint = Record<string, unknown>;

function toChart(rows: TelemetryPoint[]): Array<{ t: number; alt?: number | null; batt?: number | null; sol?: number | null; temp?: number | null; lux?: number | null; rssi?: number | null; sats?: number | null }> {
    const out: Array<{ t: number } & Record<string, number | null | undefined>> = [];
    for (const r of rows) {
        const t = new Date(String(r.time)).getTime();
        if (Number.isNaN(t)) continue;
        out.push({
            t,
            alt: telemetryNumber(r.altitude_m),
            batt: telemetryNumber(r.battery_voltage),
            sol: telemetryNumber(r.solar_voltage),
            temp: telemetryNumber(r.temperature),
            lux: telemetryNumber(r.ambient_lux),
            rssi: telemetryNumber(r.rssi),
            sats: telemetryNumber(r.gps_satellites),
        });
    }
    return out.sort((a, b) => a.t - b.t);
}

const RANGES = [
    { label: '1H', hrs: 1 },
    { label: '6H', hrs: 6 },
    { label: '12H', hrs: 12 },
    { label: 'ALL', hrs: null },
] as const;

interface MobileTelemetryTabProps {
    deviceId: string | null;
    telemetryRows: TelemetryPoint[];
}

export default function MobileTelemetryTab({ deviceId, telemetryRows }: MobileTelemetryTabProps) {
    const [rangeHr, setRangeHr] = useState<number | null>(null);

    const full = useMemo(() => toChart(telemetryRows), [telemetryRows]);
    const slice = useMemo(() => {
        const windowMs = rangeHr != null ? rangeHr * 3600 * 1000 : null;
        if (!full.length || windowMs == null) return full;
        const tCut = Date.now() - windowMs;
        return full.filter((r) => r.t >= tCut);
    }, [full, rangeHr]);

    const last = slice.at(-1);
    const lastBatt = telemetryNumber(last?.batt ?? null);
    const lastAlt = telemetryNumber(last?.alt ?? null);
    const lastTemp = telemetryNumber(last?.temp ?? null);
    const lastSol = telemetryNumber(last?.sol ?? null);
    const lastLux = telemetryNumber(last?.lux ?? null);
    const lastRssi = telemetryNumber(last?.rssi ?? null);
    const lastSats = telemetryNumber(last?.sats ?? null);

    const label = rangeHr == null ? 'ALL' : RANGES.find((r) => r.hrs === rangeHr)?.label ?? 'ALL';

    if (!deviceId) {
        return (
            <div
                className="flex h-full flex-col items-center justify-center px-8 text-center"
                style={{
                    paddingBottom: 120,
                    background: 'var(--bg)',
                    color: 'var(--text)',
                    fontFamily: 'var(--sans)',
                }}>
                <p className="text-[14px]" style={{ color: 'var(--text-dim2)' }}>
                    Pick a payload from Fleet, then chart its last-day telemetry here.
                </p>
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col overflow-hidden pb-[calc(92px+env(safe-area-inset-bottom))]" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
            <SlHeader sub={deviceId.toUpperCase()} title="Telemetry" right={<span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)' }}>{label}</span>} />

            <div className="flex gap-1 border-b px-5 py-3" style={{ borderColor: 'var(--border)' }}>
                {RANGES.map((r) => {
                    const on = rangeHr === r.hrs;
                    const click = () => setRangeHr(r.hrs);
                    return (
                        <button
                            key={r.label}
                            type="button"
                            onClick={click}
                            className="flex-1 py-2 text-[11px] font-medium uppercase tracking-[0.08em]"
                            style={{
                                border: `1px solid ${on ? 'var(--ok)' : 'var(--border-hi)'}`,
                                background: on ? 'var(--ok-soft)' : 'transparent',
                                color: on ? 'var(--ok)' : 'var(--text-dim)',
                                fontFamily: 'var(--sans)',
                            }}>
                            {r.label}
                        </button>
                    );
                })}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
                <StackedLineChart title="Altitude" valueDisplay={lastAlt != null ? Math.round(lastAlt) : '—'} unitSuffix=" m" data={slice} getY={(row) => row.alt ?? null} color="var(--ok)" />
                <StackedLineChart
                    title="Battery"
                    valueDisplay={lastBatt != null ? lastBatt.toFixed(2) : '—'}
                    unitSuffix=" V"
                    data={slice}
                    getY={(row) => row.batt ?? null}
                    min={3.2}
                    max={5.6}
                />
                <StackedLineChart title="Solar" valueDisplay={lastSol != null ? lastSol.toFixed(2) : '—'} unitSuffix=" V" data={slice} getY={(row) => row.sol ?? null} min={0} max={6} />
                <StackedLineChart title="Temperature" valueDisplay={lastTemp != null ? lastTemp.toFixed(1) : '—'} unitSuffix=" °C" data={slice} getY={(row) => row.temp ?? null} />
                <StackedLineChart title="Ambient lux" valueDisplay={lastLux != null ? String(Math.round(lastLux)) : '—'} unitSuffix=" lx" data={slice} getY={(row) => row.lux ?? null} color="var(--neutral)" />
                <StackedLineChart title="RSSI" valueDisplay={lastRssi != null ? String(Math.round(lastRssi)) : '—'} unitSuffix=" dBm" data={slice} getY={(row) => row.rssi ?? null} />
                <StackedLineChart title="GPS satellites" valueDisplay={lastSats != null ? String(Math.round(lastSats)) : '—'} data={slice} getY={(row) => row.sats ?? null} min={0} max={28} />

                <SectionLabel>Session</SectionLabel>
                <div style={{ padding: '12px 20px 96px', fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--text-dim2)' }}>
                    {telemetryRows.length} packets sampled for charts (server: last 24h).
                </div>
            </div>
        </div>
    );
}
