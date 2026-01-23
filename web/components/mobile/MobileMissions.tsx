'use client';

import { useState } from 'react';
import { Plus, Rocket } from 'lucide-react';

interface BalloonData {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
}

interface MobileMissionsProps {
    balloonData: BalloonData[];
    onBalloonClick: (balloonId: string) => void;
    onLaunch: () => void;
}

export default function MobileMissions({ balloonData, onBalloonClick, onLaunch }: MobileMissionsProps) {
    const activeBalloons = balloonData.filter(b => b.altitude_m > 100);
    const landedBalloons = balloonData.filter(b => b.altitude_m <= 100);

    return (
        <div className="h-full bg-[#1a1a1a] overflow-y-auto pb-20">
            {/* Header */}
            <div className="sticky top-0 bg-[#1a1a1a] border-b border-[#333] z-10 p-4">
                <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">My Missions</h1>
                <p className="text-[12px] text-[#666] font-mono">
                    {activeBalloons.length} active, {landedBalloons.length} landed
                </p>
            </div>

            {/* Launch Button - Giant, Prominent */}
            <div className="p-4 border-b border-[#333]">
                <button
                    onClick={onLaunch}
                    className="w-full bg-[#4a90d9] hover:bg-[#4a90d9]/90 text-white font-mono text-[16px] font-semibold py-6 rounded-lg flex items-center justify-center gap-3 min-h-[64px] transition-colors"
                >
                    <Plus size={24} />
                    Launch New Mission
                </button>
            </div>

            {/* Active Balloons */}
            {activeBalloons.length > 0 && (
                <div className="p-4">
                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-3">Active</div>
                    <div className="space-y-2">
                        {activeBalloons.map((balloon) => (
                            <button
                                key={balloon.id}
                                onClick={() => onBalloonClick(balloon.id)}
                                className="w-full bg-[#141414] border border-[#333] hover:border-[#4a90d9] p-4 rounded-lg text-left transition-colors min-h-[64px]"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 bg-[#4a9] rounded-full animate-pulse" />
                                        <span className="font-mono text-[14px] text-[#4a90d9] font-semibold">{balloon.id}</span>
                                    </div>
                                    <Rocket size={16} className="text-[#666]" />
                                </div>
                                <div className="font-mono text-[11px] text-[#999] space-y-0.5">
                                    <div>Alt: {(balloon.altitude_m * 3.28084 / 1000).toFixed(1)}k ft</div>
                                    <div>{balloon.lat.toFixed(4)}°, {balloon.lon.toFixed(4)}°</div>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Landed Balloons */}
            {landedBalloons.length > 0 && (
                <div className="p-4 border-t border-[#333]">
                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-3">Landed</div>
                    <div className="space-y-2">
                        {landedBalloons.map((balloon) => (
                            <button
                                key={balloon.id}
                                onClick={() => onBalloonClick(balloon.id)}
                                className="w-full bg-[#141414] border border-[#333] hover:border-[#666] p-4 rounded-lg text-left transition-colors min-h-[64px]"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 bg-[#666] rounded-full" />
                                        <span className="font-mono text-[14px] text-[#666] font-semibold">{balloon.id}</span>
                                    </div>
                                </div>
                                <div className="font-mono text-[11px] text-[#999] space-y-0.5">
                                    <div>Alt: {balloon.altitude_m.toFixed(0)}m</div>
                                    <div>{balloon.lat.toFixed(4)}°, {balloon.lon.toFixed(4)}°</div>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {balloonData.length === 0 && (
                <div className="flex flex-col items-center justify-center h-64 p-4 text-center">
                    <Rocket size={48} className="text-[#666] mb-4" />
                    <p className="text-[#666] text-[14px] mb-2">No missions yet</p>
                    <p className="text-[#999] text-[12px] font-mono">Launch your first balloon to get started</p>
                </div>
            )}
        </div>
    );
}
