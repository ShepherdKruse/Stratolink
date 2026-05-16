'use client';

import { TrendingUp, Globe, Cloud } from 'lucide-react';

interface MobileIntelProps {
    activeCount: number;
    landedCount: number;
    totalTracked: number;
    connectionStatus?: 'connected' | 'disconnected' | 'error';
    lastUpdate?: Date;
    balloonData?: Array<{
        id: string;
        lat: number;
        lon: number;
        altitude_m: number;
        launcher_name?: string;
        battery_voltage?: number | null;
        awaiting_gps?: boolean;
    }>;
}

function formatAltitudeFt(meters: number): string {
    if (!Number.isFinite(meters)) return '—';
    const ft = meters * 3.28084;
    return ft >= 1000 ? `${(ft / 1000).toFixed(1)}k ft` : `${Math.round(ft)} ft`;
}

function formatBattery(volts: number | null | undefined): string {
    if (volts == null || Number.isNaN(volts)) return '—';
    return `${volts.toFixed(2)} V`;
}

export default function MobileIntel({
    activeCount,
    landedCount,
    totalTracked,
    connectionStatus = 'disconnected',
    lastUpdate,
    balloonData = [],
}: MobileIntelProps) {
    const sortedByAltitude = [...balloonData].sort((a, b) => (b.altitude_m ?? 0) - (a.altitude_m ?? 0)).slice(0, 8);

    const airborne = balloonData.filter((b) => !b.awaiting_gps && b.altitude_m > 100);

    let avgAltitudeM: number | null = null;
    if (airborne.length > 0) {
        const sum = airborne.reduce((s, b) => s + Math.max(0, b.altitude_m), 0);
        avgAltitudeM = Math.round(sum / airborne.length);
    }

    return (
        <div className="h-full bg-[#1a1a1a] overflow-y-auto pb-20">
            {/* Header */}
            <div className="sticky top-0 bg-[#1a1a1a] border-b border-[#333] z-10 p-4">
                <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">Intel</h1>
                <p className="text-[12px] text-[#666] font-mono">Global fleet statistics</p>
            </div>

            {/* Global Stats */}
            <div className="p-4 space-y-4">
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <Globe size={20} className="text-[#4a90d9]" />
                        <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider">Fleet Status</div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <div className="text-[24px] font-mono text-[#4a90d9] font-bold">{activeCount}</div>
                            <div className="text-[10px] text-[#666] mt-1">Transmitting</div>
                            <div className="text-[9px] text-[#555] font-mono mt-0.5">last 2h</div>
                        </div>
                        <div>
                            <div className="text-[24px] font-mono text-[#e5e5e5] font-bold">{landedCount}</div>
                            <div className="text-[10px] text-[#666] mt-1">Near ground</div>
                            <div className="text-[9px] text-[#555] font-mono mt-0.5">&lt;100m • 24h</div>
                        </div>
                        <div>
                            <div className="text-[24px] font-mono text-[#e5e5e5] font-bold">{totalTracked}</div>
                            <div className="text-[10px] text-[#666] mt-1">Registered</div>
                            <div className="text-[9px] text-[#555] font-mono mt-0.5">status flying</div>
                        </div>
                    </div>
                </div>

                {/* Highest altitude — from live telemetry */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <TrendingUp size={20} className="text-[#4a90d9]" />
                        <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider">Fleet by altitude</div>
                    </div>
                    <div className="space-y-2">
                        {sortedByAltitude.length > 0 ? (
                            sortedByAltitude.map((entry, i) => (
                                <div
                                    key={entry.id}
                                    className="flex items-center justify-between p-3 bg-[#1a1a1a] border border-[#333] rounded">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <div className="w-6 h-6 shrink-0 rounded-full bg-[#4a90d9] flex items-center justify-center text-[10px] font-mono text-white font-bold">
                                            {i + 1}
                                        </div>
                                        <div className="min-w-0">
                                            <div className="font-mono text-[12px] text-[#e5e5e5] font-semibold truncate">{entry.id}</div>
                                            <div className="font-mono text-[10px] text-[#666] truncate">
                                                {entry.launcher_name || '—'}
                                                {entry.awaiting_gps ? ' · awaiting GPS' : ''}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="text-right shrink-0">
                                        <div className="text-[11px] text-[#4a90d9] font-mono font-semibold">{formatAltitudeFt(entry.altitude_m)}</div>
                                        <div className="text-[10px] text-[#666] font-mono">{formatBattery(entry.battery_voltage)}</div>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="text-[11px] text-[#666] font-mono py-2">No devices on the map yet</div>
                        )}
                    </div>
                </div>

                {/* Environmental Conditions - From Balloons */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <Cloud size={20} className="text-[#4a90d9]" />
                        <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider">Fleet conditions</div>
                    </div>
                    {balloonData.length > 0 ? (
                        <div className="space-y-3">
                            <div>
                                <div className="flex justify-between items-center mb-1">
                                    <span className="text-[11px] text-[#999] font-mono">Avg altitude (in flight)</span>
                                    <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">
                                        {avgAltitudeM != null ? `${avgAltitudeM}m` : '—'}
                                    </span>
                                </div>
                                <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-[#4a90d9]"
                                        style={{
                                            width: `${avgAltitudeM != null ? Math.min(100, (avgAltitudeM / 40000) * 100) : 0}%`,
                                        }}
                                    />
                                </div>
                            </div>
                            <div>
                                <div className="flex justify-between items-center mb-1">
                                    <span className="text-[11px] text-[#999] font-mono">In flight (&gt;100m)</span>
                                    <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">
                                        {airborne.length} / {balloonData.length}
                                    </span>
                                </div>
                                <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-[#4a90d9]"
                                        style={{
                                            width: `${balloonData.length > 0 ? (airborne.length / balloonData.length) * 100 : 0}%`,
                                        }}
                                    />
                                </div>
                            </div>
                            <div>
                                <div className="flex justify-between items-center mb-1">
                                    <span className="text-[11px] text-[#999] font-mono">Awaiting GPS fix</span>
                                    <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">
                                        {balloonData.filter((b) => b.awaiting_gps).length}
                                    </span>
                                </div>
                                <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-[#4a90d9]"
                                        style={{
                                            width: `${balloonData.length > 0 ? (balloonData.filter((b) => b.awaiting_gps).length / balloonData.length) * 100 : 0}%`,
                                        }}
                                    />
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="text-[11px] text-[#666] font-mono py-2">No fleet data to summarize</div>
                    )}
                </div>

                {/* System Status */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider mb-3">System Status</div>
                    <div className="space-y-2 font-mono text-[11px]">
                        <div className="flex justify-between">
                            <span className="text-[#999]">Database</span>
                            <span
                                className={
                                    connectionStatus === 'connected'
                                        ? 'text-[#4a9]'
                                        : connectionStatus === 'error'
                                          ? 'text-[#c44]'
                                          : 'text-[#b84]'
                                }>
                                {connectionStatus.toUpperCase()}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-[#999]">Last fleet refresh</span>
                            <span className="text-[#e5e5e5]">
                                {lastUpdate ? lastUpdate.toISOString().substring(11, 19) : '—'}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-[#999]">Refresh rate</span>
                            <span className="text-[#e5e5e5]">30s</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
