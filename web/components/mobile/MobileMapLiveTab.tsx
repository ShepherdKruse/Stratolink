'use client';

import MobileRadar from './MobileRadar';
import type { MobileFleetDeviceRow } from './mobileStratolinkUtils';
import { fmtCoords, formatAge } from './mobileStratolinkUtils';
import { parseGateways } from './mobileGatewayGeo';

interface MobileMapLiveTabProps {
    balloonData: MobileFleetDeviceRow[];
    flightPathData: Array<{ lat: number; lon: number; time: Date }>;
    selectedBalloonId: string | null;
    onSelectDevice: (id: string | null) => void;
    userLocation: { lat: number; lon: number } | null;
    latestRow: Record<string, unknown> | undefined;
}

function coerceNum(v: unknown): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/** Map tab: real Mapbox + prototype-style floating capsule + LIVE VITALS band above the tab bar. */
export default function MobileMapLiveTab({
    balloonData,
    flightPathData,
    selectedBalloonId,
    onSelectDevice,
    userLocation,
    latestRow,
}: MobileMapLiveTabProps) {
    const sel = balloonData.find((b) => b.id === selectedBalloonId);
    const mapGateways = parseGateways(latestRow?.gateways);
    const rssi =
        typeof latestRow?.rssi === 'number'
            ? latestRow.rssi
            : sel?.rssi != null
              ? sel.rssi
              : undefined;
    const satsRaw = typeof latestRow?.gps_satellites === 'number' ? latestRow.gps_satellites : sel?.gps_satellites ?? undefined;

    const liveIso = sel?.last_contact ?? null;

    const battVolts = coerceNum(latestRow?.battery_voltage) ?? coerceNum(sel?.battery_voltage ?? null);

    const alt =
        sel && !sel.awaiting_gps
            ? coerceNum(latestRow?.altitude_m) ?? sel.altitude_m
            : coerceNum(latestRow?.altitude_m);

    const tabBarReserve = `calc(5.85rem + max(34px, env(safe-area-inset-bottom)))`;

    return (
        <div className="relative h-full w-full">
            <div className="absolute inset-0 z-0">
                <MobileRadar
                    balloonData={balloonData}
                    flightPathData={selectedBalloonId ? flightPathData : []}
                    onBalloonClick={(id) => onSelectDevice(id)}
                    userLocation={userLocation}
                    selectedBalloonId={selectedBalloonId}
                    gateways={mapGateways}
                />
            </div>

            <div
                className="pointer-events-none absolute left-4 right-4 z-40 flex items-start gap-2"
                style={{ top: `max(12px, env(safe-area-inset-top))` }}>
                <div
                    className="pointer-events-auto flex min-h-[48px] min-w-0 flex-1 items-center gap-[10px] border px-4 py-2"
                    style={{ background: 'rgba(11, 14, 19, 0.78)', borderColor: 'var(--border-hi)', backdropFilter: 'blur(20px)' }}>
                    <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-[var(--ok)]" />
                    <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-[13px] font-medium" style={{ color: 'var(--text-hi)' }}>
                            {selectedBalloonId ?? 'Tap marker'}
                        </div>
                        <div className="truncate font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            {sel ? fmtCoords(sel.lat, sel.lon) : 'Fleet overview'}
                        </div>
                    </div>
                    {selectedBalloonId ? (
                        <button
                            type="button"
                            aria-label="Clear selection"
                            onClick={() => onSelectDevice(null)}
                            className="pointer-events-auto shrink-0 bg-transparent px-1 font-mono text-[17px]"
                            style={{ color: 'var(--text-dim)', lineHeight: 1 }}>
                            ×
                        </button>
                    ) : null}
                </div>
            </div>

            <div
                className="absolute left-0 right-0 z-[35] border-t"
                style={{
                    bottom: tabBarReserve,
                    background: 'rgba(11, 14, 19, 0.88)',
                    borderColor: 'var(--border-hi)',
                    backdropFilter: 'blur(24px)',
                }}>
                <div className="flex justify-center pt-3 pb-1">
                    <div className="h-1 w-9 rounded bg-[var(--text-dim3)]" />
                </div>
                <div className="px-5 pb-5">
                    <div className="mb-4 flex justify-between gap-2">
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>
                            Live vitals
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim3)' }}>
                            uplink {formatAge(liveIso)}
                        </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                        <VitalsUnit label="Alt" value={typeof alt === 'number' && Number.isFinite(alt) ? String(Math.round(alt)) : '—'} suf="m" />
                        <VitalsUnit label="Batt" value={battVolts != null ? battVolts.toFixed(2) : '—'} suf="V" />
                        <VitalsUnit label="RSSI" value={rssi != null ? String(Math.round(rssi)) : '—'} suf="dBm" />
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--text-dim2)' }}>
                                Sats
                            </div>
                            <div
                                className="font-mono text-[14px] font-medium"
                                style={{
                                    marginTop: 4,
                                    color:
                                        typeof satsRaw === 'number' && satsRaw > 0 ? 'var(--text-hi)' : 'var(--alert)',
                                    fontVariantNumeric: 'tabular-nums',
                                }}>
                                {satsRaw ?? '—'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function VitalsUnit({ label, value, suf }: { label: string; value: string; suf?: string }) {
    return (
        <div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--text-dim2)' }}>{label}</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, marginTop: 4, color: 'var(--text-hi)', fontVariantNumeric: 'tabular-nums' }}>
                {value}
                {suf ? <span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>{suf}</span> : null}
            </div>
        </div>
    );
}
