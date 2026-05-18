'use client';

import { useMemo, useState } from 'react';
import { SectionLabel, SlHeader, StackedLineChart } from './mobileStratolinkUi';
import { altitudeFromPressureHpa } from '@/lib/atmosphere/isa';

type TelemetryPoint = Record<string, unknown>;

function coerceNum(v: unknown): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/* Gateway count is derived per-row by reading rx_metadata.length from the
 * `gateways` JSONB column. We tolerate either a parsed array (the normal
 * Supabase path) or a JSON string in case an upstream cache stringifies it. */
function gatewayCount(raw: unknown): number | null {
    if (!raw) return null;
    let arr: unknown = raw;
    if (typeof raw === 'string') {
        try {
            arr = JSON.parse(raw);
        } catch {
            return null;
        }
    }
    return Array.isArray(arr) ? arr.length : null;
}

function toChart(rows: TelemetryPoint[]): Array<{ t: number; alt?: number | null; presAlt?: number | null; pres?: number | null; batt?: number | null; sol?: number | null; temp?: number | null; lux?: number | null; rssi?: number | null; sats?: number | null; gws?: number | null }> {
    const out: Array<{ t: number } & Record<string, number | null | undefined>> = [];
    for (const r of rows) {
        const t = new Date(String(r.time)).getTime();
        if (Number.isNaN(t)) continue;
        const pres = coerceNum(r.pressure);
        out.push({
            t,
            alt: coerceNum(r.altitude_m),
            pres,
            /* USSA-1976 pressure altitude is computed at the boundary so the
             * chart and any per-row tooltip read the same value. The barometer
             * keeps producing fresh readings even when the MAX-M10S has lost
             * GPS lock — see web/lib/atmosphere/isa.ts header for context. */
            presAlt: altitudeFromPressureHpa(pres),
            batt: coerceNum(r.battery_voltage),
            sol: coerceNum(r.solar_voltage),
            temp: coerceNum(r.temperature),
            lux: coerceNum(r.ambient_lux),
            rssi: coerceNum(r.rssi),
            sats: coerceNum(r.gps_satellites),
            gws: gatewayCount(r.gateways),
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
    const lastBatt = coerceNum(last?.batt ?? null);
    const lastAlt = coerceNum(last?.alt ?? null);
    const lastPresAlt = coerceNum(last?.presAlt ?? null);
    const lastPres = coerceNum(last?.pres ?? null);
    const lastTemp = coerceNum(last?.temp ?? null);
    const lastSol = coerceNum(last?.sol ?? null);
    const lastLux = coerceNum(last?.lux ?? null);
    const lastRssi = coerceNum(last?.rssi ?? null);
    const lastSats = coerceNum(last?.sats ?? null);
    const lastGws = coerceNum(last?.gws ?? null);

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
                {/* GPS altitude and pressure-derived altitude charted as
                  * adjacent rows so the operator can spot divergence at a
                  * glance. The pressure altitude is the more reliable of the
                  * two when GPS is intermittent — see web/lib/atmosphere. */}
                <StackedLineChart title="Altitude · GPS" valueDisplay={lastAlt != null ? Math.round(lastAlt) : '—'} unitSuffix=" m" data={slice} getY={(row) => row.alt ?? null} color="var(--ok)" />
                <StackedLineChart title="Altitude · Pressure" valueDisplay={lastPresAlt != null ? Math.round(lastPresAlt) : '—'} unitSuffix=" m" data={slice} getY={(row) => row.presAlt ?? null} color="var(--ok)" />
                <StackedLineChart title="Pressure" valueDisplay={lastPres != null ? lastPres.toFixed(1) : '—'} unitSuffix=" hPa" data={slice} getY={(row) => row.pres ?? null} color="var(--neutral)" />
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
                {/* Gateway count traces link diversity — at altitude a healthy
                  * pico-balloon hits 5–30 gateways per packet, and a sudden
                  * collapse to 1 typically precedes loss of contact, so this
                  * row is the most useful early-warning signal we have. */}
                <StackedLineChart title="Gateways heard" valueDisplay={lastGws != null ? String(Math.round(lastGws)) : '—'} data={slice} getY={(row) => row.gws ?? null} min={0} color="var(--ok)" />
                <StackedLineChart title="GPS satellites" valueDisplay={lastSats != null ? String(Math.round(lastSats)) : '—'} data={slice} getY={(row) => row.sats ?? null} min={0} max={28} />

                <SectionLabel>Session</SectionLabel>
                <div style={{ padding: '12px 20px 96px', fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--text-dim2)' }}>
                    {telemetryRows.length} packets since launch (full mission while flying).
                </div>
            </div>
        </div>
    );
}
