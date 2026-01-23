'use client';

import { useState, useEffect } from 'react';

interface PilotHUDProps {
    activeBalloonId: string | null;
    balloonData?: {
        id: string;
        lat: number;
        lon: number;
        altitude_m: number;
        battery_voltage?: number;
        velocity_heading?: number;
    } | null;
    onExit?: () => void;
    onToggleSidebar?: () => void;
    isSidebarOpen?: boolean;
}

export default function PilotHUD({ activeBalloonId, balloonData, onExit, onToggleSidebar, isSidebarOpen }: PilotHUDProps) {
    if (!activeBalloonId || !balloonData) {
        return null;
    }

    const batteryVoltage = balloonData.battery_voltage ?? 3.7;
    const batteryPercentage = Math.min(100, Math.max(0, ((batteryVoltage - 3.0) / (4.2 - 3.0)) * 100));
    const altitudeFt = balloonData.altitude_m * 3.28084;
    const altitudeKm = balloonData.altitude_m / 1000;

    const [utcTime, setUtcTime] = useState(new Date().toISOString().substring(0, 19).replace('T', ' '));
    
    useEffect(() => {
        const interval = setInterval(() => {
            setUtcTime(new Date().toISOString().substring(0, 19).replace('T', ' '));
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    // Format coordinates in decimal degrees (explicit, machine-readable)
    const formatCoord = (coord: number, isLat: boolean) => {
        const dir = isLat ? (coord >= 0 ? 'N' : 'S') : (coord >= 0 ? 'E' : 'W');
        return `${Math.abs(coord).toFixed(6)}° ${dir}`;
    };

    return (
        <div className={`absolute inset-0 pointer-events-none z-20 transition-transform duration-300 ${isSidebarOpen ? 'translate-x-[-260px]' : ''}`}>
            {/* Top Left: Primary Data Panel */}
            <div className="absolute top-3 left-3">
                <div className="bg-[#1a1a1a]/95 border border-[#333] p-3 min-w-[200px]">
                    {/* Device ID */}
                    <div className="flex items-baseline justify-between border-b border-[#333] pb-2 mb-2">
                        <span className="text-[10px] font-semibold text-[#666] uppercase tracking-wider">Device</span>
                        <span className="font-mono text-[12px] text-[#4a90d9] font-semibold">{activeBalloonId}</span>
                    </div>

                    {/* Time */}
                    <div className="mb-3">
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-1">Time (UTC)</div>
                        <div className="font-mono text-[14px] text-[#e5e5e5] font-semibold">{utcTime}</div>
                    </div>

                    {/* Position */}
                    <div className="mb-3">
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-1">Position</div>
                        <div className="font-mono text-[11px] text-[#e5e5e5] space-y-0.5">
                            <div>lat: {formatCoord(balloonData.lat, true)}</div>
                            <div>lon: {formatCoord(balloonData.lon, false)}</div>
                        </div>
                    </div>

                    {/* Altitude - dual units, explicit */}
                    <div>
                        <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-1">Altitude</div>
                        <div className="font-mono text-[11px] text-[#e5e5e5] space-y-0.5">
                            <div className="flex justify-between">
                                <span className="text-[#999]">meters</span>
                                <span className="font-semibold">{balloonData.altitude_m.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-[#999]">feet</span>
                                <span>{altitudeFt.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-[#999]">km</span>
                                <span>{altitudeKm.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Top Right: Controls + Power */}
            <div className="absolute top-3 right-3 space-y-2">
                {/* Exit button */}
                <button
                    onClick={onExit}
                    className="bg-[#1a1a1a]/95 border border-[#333] hover:border-[#c44] text-[#999] hover:text-[#c44] px-3 py-1.5 text-[11px] font-mono transition-colors pointer-events-auto block w-full"
                >
                    [ESC] Exit
                </button>
                
                {/* Systems toggle */}
                {onToggleSidebar && (
                    <button
                        onClick={onToggleSidebar}
                        className={`bg-[#1a1a1a]/95 border px-3 py-1.5 text-[11px] font-mono transition-colors pointer-events-auto block w-full ${
                            isSidebarOpen
                                ? 'border-[#4a90d9] text-[#4a90d9]'
                                : 'border-[#333] text-[#999] hover:border-[#666] hover:text-[#e5e5e5]'
                        }`}
                    >
                        {isSidebarOpen ? '[S] Internals ▸' : '[S] Internals'}
                    </button>
                )}

                {/* Power State */}
                <div className="bg-[#1a1a1a]/95 border border-[#333] p-3 min-w-[140px]">
                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Power</div>
                    <div className="font-mono text-[11px] space-y-1">
                        <div className="flex justify-between">
                            <span className="text-[#999]">V_bat</span>
                            <span className="text-[#e5e5e5] font-semibold">{batteryVoltage.toFixed(2)}V</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-[#999]">capacity</span>
                            <span className={batteryPercentage > 30 ? 'text-[#4a9]' : batteryPercentage > 15 ? 'text-[#b84]' : 'text-[#c44]'}>
                                {batteryPercentage.toFixed(0)}%
                            </span>
                        </div>
                        {/* Visual bar - minimal */}
                        <div className="h-1 bg-[#333] mt-1">
                            <div 
                                className={`h-full ${batteryPercentage > 30 ? 'bg-[#4a9]' : batteryPercentage > 15 ? 'bg-[#b84]' : 'bg-[#c44]'}`}
                                style={{ width: `${batteryPercentage}%` }}
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Side: Altitude Scale */}
            <div className="absolute top-1/2 right-3 transform -translate-y-1/2">
                <div className="bg-[#1a1a1a]/95 border border-[#333] p-2">
                    <div className="text-[9px] font-semibold text-[#666] uppercase tracking-wider mb-2 text-center">ALT (ft)</div>
                    <div className="relative w-8 h-[180px]">
                        {/* Scale ticks */}
                        <div className="absolute inset-0 flex flex-col justify-between">
                            {[100, 80, 60, 40, 20, 0].map((val) => (
                                <div key={val} className="flex items-center justify-end gap-1">
                                    <span className="text-[8px] font-mono text-[#666]">{val}k</span>
                                    <div className="w-1 h-px bg-[#333]" />
                                </div>
                            ))}
                        </div>
                        {/* Current position */}
                        <div 
                            className="absolute left-0 right-0 h-px bg-[#4a90d9]"
                            style={{ bottom: `${Math.min(100, (altitudeFt / 100000) * 100)}%` }}
                        >
                            <div className="absolute right-full mr-1 top-1/2 -translate-y-1/2">
                                <span className="text-[9px] font-mono text-[#4a90d9] font-semibold whitespace-nowrap">
                                    {(altitudeFt / 1000).toFixed(1)}k
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Bottom Left: Heading/Track */}
            <div className="absolute bottom-3 left-3">
                <div className="bg-[#1a1a1a]/95 border border-[#333] p-3">
                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Track</div>
                    <div className="font-mono text-[11px] space-y-1">
                        <div className="flex justify-between gap-4">
                            <span className="text-[#999]">heading</span>
                            <span className="text-[#e5e5e5]">{(balloonData.velocity_heading ?? 90).toFixed(1)}°</span>
                        </div>
                        <div className="flex justify-between gap-4">
                            <span className="text-[#999]">ground_spd</span>
                            <span className="text-[#e5e5e5]">45.2 m/s</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
