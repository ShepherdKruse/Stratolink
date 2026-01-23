'use client';

import { TrendingUp, Globe, Cloud } from 'lucide-react';

interface MobileIntelProps {
    activeCount: number;
    landedCount: number;
    totalTracked: number;
    connectionStatus?: 'connected' | 'disconnected' | 'error';
    lastUpdate?: Date;
}

export default function MobileIntel({ activeCount, landedCount, totalTracked, connectionStatus = 'disconnected', lastUpdate }: MobileIntelProps) {
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
                            <div className="text-[10px] text-[#666] mt-1">Active</div>
                        </div>
                        <div>
                            <div className="text-[24px] font-mono text-[#e5e5e5] font-bold">{landedCount}</div>
                            <div className="text-[10px] text-[#666] mt-1">Landed</div>
                        </div>
                        <div>
                            <div className="text-[24px] font-mono text-[#e5e5e5] font-bold">{totalTracked}</div>
                            <div className="text-[10px] text-[#666] mt-1">Total</div>
                        </div>
                    </div>
                </div>

                {/* Leaderboard */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <TrendingUp size={20} className="text-[#4a90d9]" />
                        <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider">Top Performers</div>
                    </div>
                    <div className="space-y-2">
                        {[
                            { id: 'Balloon-042', distance: '12,847 km', altitude: '32.4k ft' },
                            { id: 'Balloon-019', distance: '9,234 km', altitude: '28.1k ft' },
                            { id: 'Balloon-033', distance: '7,891 km', altitude: '30.2k ft' },
                        ].map((entry, i) => (
                            <div key={i} className="flex items-center justify-between p-3 bg-[#1a1a1a] border border-[#333] rounded">
                                <div className="flex items-center gap-3">
                                    <div className="w-6 h-6 rounded-full bg-[#4a90d9] flex items-center justify-center text-[10px] font-mono text-white font-bold">
                                        {i + 1}
                                    </div>
                                    <div>
                                        <div className="font-mono text-[12px] text-[#e5e5e5] font-semibold">{entry.id}</div>
                                        <div className="font-mono text-[10px] text-[#666]">{entry.distance}</div>
                                    </div>
                                </div>
                                <div className="text-[10px] text-[#666] font-mono">{entry.altitude}</div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Weather Predictions */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <Cloud size={20} className="text-[#4a90d9]" />
                        <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider">Weather Forecast</div>
                    </div>
                    <div className="space-y-3">
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <span className="text-[11px] text-[#999] font-mono">Jet Stream (30k ft)</span>
                                <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">110 mph →</span>
                            </div>
                            <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                <div className="h-full bg-[#4a90d9]" style={{ width: '75%' }} />
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <span className="text-[11px] text-[#999] font-mono">Wind Speed (20k ft)</span>
                                <span className="text-[12px] text-[#4a90d9] font-mono font-semibold">85 mph ↖</span>
                            </div>
                            <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                <div className="h-full bg-[#4a90d9]" style={{ width: '60%' }} />
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <span className="text-[11px] text-[#999] font-mono">Stratospheric Temp</span>
                                <span className="text-[12px] text-[#c44] font-mono font-semibold">-45°C</span>
                            </div>
                            <div className="h-1 bg-[#333] rounded-full overflow-hidden">
                                <div className="h-full bg-[#c44]" style={{ width: '20%' }} />
                            </div>
                        </div>
                    </div>
                </div>

                {/* System Status */}
                <div className="bg-[#141414] border border-[#333] rounded-lg p-4">
                    <div className="text-[12px] font-semibold text-[#666] uppercase tracking-wider mb-3">System Status</div>
                    <div className="space-y-2 font-mono text-[11px]">
                        <div className="flex justify-between">
                            <span className="text-[#999]">Database</span>
                            <span className={
                                connectionStatus === 'connected' ? 'text-[#4a9]' : 
                                connectionStatus === 'error' ? 'text-[#c44]' : 
                                'text-[#b84]'
                            }>
                                {connectionStatus.toUpperCase()}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-[#999]">Last Update</span>
                            <span className="text-[#e5e5e5]">
                                {lastUpdate ? lastUpdate.toISOString().substring(11, 19) : '—'}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-[#999]">Refresh Rate</span>
                            <span className="text-[#e5e5e5]">30s</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
