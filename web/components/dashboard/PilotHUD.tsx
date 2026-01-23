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

    // Mock data with defaults
    const batteryVoltage = balloonData.battery_voltage ?? 3.7;
    const batteryPercentage = Math.min(100, Math.max(0, ((batteryVoltage - 3.0) / (4.2 - 3.0)) * 100));
    const altitudeFt = balloonData.altitude_m * 3.28084; // Convert meters to feet
    const maxAltitude = 100000; // 100k feet max for tape
    const altitudePercentage = Math.min(100, (altitudeFt / maxAltitude) * 100);

    // Get current UTC time
    const [utcTime, setUtcTime] = useState(new Date().toISOString().substring(11, 19));
    
    useEffect(() => {
        const interval = setInterval(() => {
            setUtcTime(new Date().toISOString().substring(11, 19));
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    // Format coordinates
    const formatCoord = (coord: number, isLat: boolean) => {
        const abs = Math.abs(coord);
        const deg = Math.floor(abs);
        const min = Math.floor((abs - deg) * 60);
        const sec = ((abs - deg) * 60 - min) * 60;
        const dir = isLat ? (coord >= 0 ? 'N' : 'S') : (coord >= 0 ? 'E' : 'W');
        return `${deg}°${min}'${sec.toFixed(1)}" ${dir}`;
    };

    return (
        <div className={`absolute inset-0 pointer-events-none z-20 transition-transform duration-500 ${isSidebarOpen ? 'translate-x-[-300px]' : ''}`}>
            {/* Top Left: Mission Clock & Coordinates */}
            <div className="absolute top-6 left-6 space-y-3">
                <div className="backdrop-blur-md bg-black/40 border border-cyan-500/30 rounded-lg p-4 font-mono">
                    <div className="text-cyan-400 text-xs uppercase tracking-wider mb-1">Mission Clock</div>
                    <div className="text-white text-2xl font-bold">{utcTime} UTC</div>
                </div>
                <div className="backdrop-blur-md bg-black/40 border border-cyan-500/30 rounded-lg p-4 font-mono">
                    <div className="text-cyan-400 text-xs uppercase tracking-wider mb-1">Coordinates</div>
                    <div className="text-white text-sm space-y-1">
                        <div>Lat: {formatCoord(balloonData.lat, true)}</div>
                        <div>Lon: {formatCoord(balloonData.lon, false)}</div>
                    </div>
                </div>
            </div>

            {/* Bottom Center: Power Core (Battery Voltage) */}
            <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2">
                <div className="backdrop-blur-md bg-black/40 border border-cyan-500/30 rounded-lg p-6">
                    <div className="text-cyan-400 text-xs uppercase tracking-wider mb-3 text-center">Power Core</div>
                    <div className="relative w-32 h-32">
                        {/* Circular Progress Ring */}
                        <svg className="transform -rotate-90 w-32 h-32">
                            <circle
                                cx="64"
                                cy="64"
                                r="56"
                                stroke="rgba(0, 255, 255, 0.2)"
                                strokeWidth="4"
                                fill="none"
                            />
                            <circle
                                cx="64"
                                cy="64"
                                r="56"
                                stroke="rgb(0, 255, 255)"
                                strokeWidth="4"
                                fill="none"
                                strokeDasharray={`${2 * Math.PI * 56}`}
                                strokeDashoffset={`${2 * Math.PI * 56 * (1 - batteryPercentage / 100)}`}
                                strokeLinecap="round"
                                className="transition-all duration-500"
                            />
                        </svg>
                        {/* Center Text */}
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <div className="text-white text-2xl font-bold">{batteryVoltage.toFixed(2)}V</div>
                            <div className="text-cyan-400 text-xs mt-1">{batteryPercentage.toFixed(0)}%</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Side: Altitude Tape */}
            <div className="absolute top-1/2 right-6 transform -translate-y-1/2">
                <div className="backdrop-blur-md bg-black/40 border border-cyan-500/30 rounded-lg p-4">
                    <div className="text-cyan-400 text-xs uppercase tracking-wider mb-3 text-center">Altitude</div>
                    <div className="relative w-16 h-64 bg-black/20 rounded border border-cyan-500/20">
                        {/* Altitude Tape Background */}
                        <div className="absolute inset-0 flex flex-col justify-between py-2">
                            {[100000, 80000, 60000, 40000, 20000, 0].map((alt) => (
                                <div key={alt} className="flex items-center justify-between px-1">
                                    <div className="text-cyan-400/60 text-[10px] font-mono">{alt.toLocaleString()}</div>
                                    <div className="w-2 h-px bg-cyan-500/40"></div>
                                </div>
                            ))}
                        </div>
                        {/* Current Altitude Indicator */}
                        <div
                            className="absolute left-0 right-0 bg-cyan-500/80 border-y border-cyan-400"
                            style={{
                                bottom: `${altitudePercentage}%`,
                                height: '2px',
                            }}
                        >
                            <div className="absolute -right-8 top-1/2 transform -translate-y-1/2 text-cyan-400 text-xs font-mono font-bold">
                                {altitudeFt.toLocaleString(undefined, { maximumFractionDigits: 0 })} ft
                            </div>
                        </div>
                        {/* Altitude Marker */}
                        <div
                            className="absolute left-0 right-0"
                            style={{
                                bottom: `${altitudePercentage}%`,
                            }}
                        >
                            <div className="absolute left-0 top-1/2 transform -translate-y-1/2 w-4 h-4 border-2 border-cyan-400 bg-cyan-500/20"></div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Exit Ride Along Button */}
            <div className="absolute top-6 right-6 space-y-3">
                <button
                    onClick={onExit}
                    className="backdrop-blur-md bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 text-red-400 px-4 py-2 rounded-lg font-medium transition-colors pointer-events-auto block w-full"
                >
                    Exit Ride Along
                </button>
                
                {/* Diagnostics/Systems Button */}
                {onToggleSidebar && (
                    <button
                        onClick={onToggleSidebar}
                        className={`backdrop-blur-md border px-6 py-3 rounded-lg font-bold text-sm uppercase tracking-wider transition-all pointer-events-auto block w-full ${
                            isSidebarOpen
                                ? 'bg-cyan-500/40 border-cyan-400 text-cyan-300 shadow-lg shadow-cyan-500/50'
                                : 'bg-cyan-500/20 hover:bg-cyan-500/30 border-cyan-500/50 text-cyan-400 hover:shadow-lg hover:shadow-cyan-500/30'
                        }`}
                    >
                        <span className="flex items-center justify-center gap-2">
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                            </svg>
                            {isSidebarOpen ? 'SYSTEMS ACTIVE' : 'SYSTEM INTERNALS'}
                        </span>
                    </button>
                )}
            </div>
        </div>
    );
}
