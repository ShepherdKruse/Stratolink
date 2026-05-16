'use client';

import { SectionLabel, SlHeader } from './mobileStratolinkUi';
import {
    deviceUiStatus,
    fmtAltM,
    fmtVolts,
    formatAge,
    pillClass,
    type MobileFleetDeviceRow,
} from './mobileStratolinkUtils';

function fmtRssi(v: number | null | undefined) {
    if (v == null || Number.isNaN(v)) return '—';
    return `${Math.round(v)} dBm`;
}

interface MobileFleetScreenProps {
    balloonData: MobileFleetDeviceRow[];
    activeTransmittingCount: number;
    fleetRegisteredCount: number;
    activeAlertsCount: number;
    connectionStatus: 'connected' | 'disconnected' | 'error';
    livePacketIso?: string | null;
    lastFleetRefreshIso?: string | null;
    onOpenDevice: (id: string) => void;
    onOpenLaunch: () => void;
}

/** Rough uplink/min from telemetry row count last 60s — optional heuristics caller */
function FleetDeviceCard({
    row,
    primary,
    onOpen,
}: {
    row: MobileFleetDeviceRow;
    primary?: boolean;
    onOpen: (id: string) => void;
}) {
    const status = deviceUiStatus(row);

    const rssi = fmtRssi(row.rssi ?? null);

    return (
        <button
            type="button"
            onClick={() => onOpen(row.id)}
            className="w-full cursor-pointer px-5 py-4 text-left"
            style={{
                borderBottom: '1px solid var(--border)',
                borderLeftWidth: primary ? 2 : 2,
                borderLeftStyle: 'solid',
                borderLeftColor: primary ? 'var(--ok)' : 'transparent',
                background: primary ? 'var(--ok-soft)' : 'transparent',
            }}>
            <div className="mb-2 flex items-center justify-between">
                <span style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, color: 'var(--text-hi)' }}>{row.id}</span>
                <span className={pillClass(status)} style={{ fontSize: 9 }}>
                    {status}
                </span>
            </div>
            <div className="mb-2 grid grid-cols-3 gap-3">
                <div>
                    <div style={{ fontSize: 9, letterSpacing: '0.12em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 3 }}>
                        ALT
                    </div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{fmtAltM(row.altitude_m, row.awaiting_gps)}</div>
                </div>
                <div>
                    <div style={{ fontSize: 9, letterSpacing: '0.12em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 3 }}>
                        BATT
                    </div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{fmtVolts(row.battery_voltage)}</div>
                </div>
                <div>
                    <div style={{ fontSize: 9, letterSpacing: '0.12em', color: 'var(--text-dim2)', textTransform: 'uppercase', fontWeight: 500, marginBottom: 3 }}>
                        RSSI
                    </div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{rssi}</div>
                </div>
            </div>
            <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                <span>
                    Seen <strong style={{ color: 'var(--text)' }}>{formatAge(row.last_contact)}</strong> ago
                </span>
                <svg width={14} height={14} viewBox="0 0 14 14" fill="none" aria-hidden style={{ opacity: 0.4 }}>
                    <path d="M 5 3 L 9 7 L 5 11" stroke="var(--text-dim)" strokeWidth="1.5" />
                </svg>
            </div>
        </button>
    );
}

export default function MobileFleetScreen({
    balloonData,
    activeTransmittingCount,
    fleetRegisteredCount,
    activeAlertsCount,
    connectionStatus,
    livePacketIso,
    lastFleetRefreshIso,
    onOpenDevice,
    onOpenLaunch,
}: MobileFleetScreenProps) {
    const sorted = [...balloonData].sort((a, b) => {
        const ao = deviceUiStatus(a) === 'TRACKING' ? 0 : 1;
        const bo = deviceUiStatus(b) === 'TRACKING' ? 0 : 1;
        if (ao !== bo) return ao - bo;
        return a.id.localeCompare(b.id);
    });
    const primaryId = sorted[0]?.id;

    const dbUi =
        connectionStatus === 'connected' ? (
            <span className="v teal">CONNECTED</span>
        ) : connectionStatus === 'error' ? (
            <span className="v" style={{ color: 'var(--alert)' }}>
                ERROR
            </span>
        ) : (
            <span className="v">OFFLINE</span>
        );

    return (
        <div className="flex h-full flex-col overflow-hidden bg-[var(--bg)] text-[var(--text)]" style={{ fontFamily: 'var(--sans)', paddingBottom: 88 }}>
            <SlHeader
                sub="GROUND STATION"
                title="Stratolink"
                right={
                    <>
                        <span style={{ fontSize: 9, letterSpacing: '0.10em', color: 'var(--ok)', textTransform: 'uppercase', fontWeight: 500 }}>● LIVE</span>
                        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim3)' }}>
                            uplink <strong style={{ color: 'var(--text)' }}>{formatAge(livePacketIso ?? lastFleetRefreshIso)}</strong> ago
                        </span>
                    </>
                }
            />

            <div className="flex-1 overflow-y-auto">
                <div className="grid grid-cols-3 border-b" style={{ borderColor: 'var(--border)' }}>
                    {[
                        { k: 'Active', v: activeTransmittingCount },
                        { k: 'Tracked', v: fleetRegisteredCount },
                        { k: 'Alerts', v: activeAlertsCount },
                    ].map(({ k, v }, i) => (
                        <div
                            key={k}
                            className="py-[18px] px-4"
                            style={{
                                borderRight:
                                    i < 2
                                        ? '1px solid var(--border)'
                                        : undefined,
                            }}>
                            <div style={{ fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>
                                {k}
                            </div>
                            <div
                                style={{
                                    fontFamily: 'var(--mono)',
                                    fontSize: 26,
                                    fontWeight: 500,
                                    marginTop: 6,
                                    lineHeight: 1,
                                    color: k === 'Alerts' && v > 0 ? 'var(--alert)' : 'var(--text-hi)',
                                }}>
                                {v}
                            </div>
                        </div>
                    ))}
                </div>

                <button type="button" onClick={onOpenLaunch} className="mx-4 mt-3 w-auto rounded px-4 py-2 text-[11px]" style={{ border: '1px solid var(--border-hi)', color: 'var(--ok)', fontFamily: 'var(--mono)' }}>
                    + Launch mission
                </button>

                <SectionLabel right={<span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim2)' }}>{balloonData.length} shown</span>}>
                    Fleet
                </SectionLabel>

                {sorted.map((row) => (
                    <FleetDeviceCard key={row.id} row={row} primary={row.id === primaryId} onOpen={onOpenDevice} />
                ))}

                {balloonData.length === 0 ? (
                    <div className="px-5 py-8 text-center" style={{ color: 'var(--text-dim2)', fontSize: 13 }}>
                        No flying payloads with a map position yet. Activate a payload or ensure launch coords are set.
                    </div>
                ) : null}

                <SectionLabel>System</SectionLabel>
                <div className="px-5 pb-24">
                    <div className="sl-kv-row">
                        <span className="k">Database</span>
                        {dbUi}
                    </div>
                    <div className="sl-kv-row">
                        <span className="k">Last telemetry (fleet-wide)</span>
                        <span className="v">{formatAge(livePacketIso ?? lastFleetRefreshIso)} ago</span>
                    </div>
                    <div className="sl-kv-row" style={{ borderBottom: 'none' }}>
                        <span className="k">Fleet sync cycle</span>
                        <span className="v">{formatAge(lastFleetRefreshIso)} ago</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
