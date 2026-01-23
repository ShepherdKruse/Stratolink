'use client';

import { useEffect } from 'react';
import Payload3DViewer from './Payload3DViewer';
import MetricSparkline from './MetricSparkline';

interface MissionSidebarProps {
    isOpen: boolean;
    onClose: () => void;
    balloonId: string;
    telemetryData?: Array<{
        time: Date | string;
        battery_voltage?: number;
        temperature?: number;
        pressure?: number;
        rssi?: number;
    }>;
}

export default function MissionSidebar({ isOpen, onClose, balloonId, telemetryData = [] }: MissionSidebarProps) {
    // Generate mock data if no telemetry data provided (for demo)
    const generateMockData = (baseValue: number, variance: number, count: number = 24) => {
        const now = new Date();
        return Array.from({ length: count }, (_, i) => {
            const time = new Date(now.getTime() - (count - i) * 60 * 60 * 1000); // Last 24 hours
            const value = baseValue + (Math.random() - 0.5) * variance;
            return { time, value: Math.max(0, value) };
        });
    };

    // Get current values (latest telemetry or mock)
    const latestTelemetry = telemetryData.length > 0 
        ? telemetryData[telemetryData.length - 1]
        : { battery_voltage: 3.72, temperature: -45.2, pressure: 120.5, rssi: -112 };

    // Prepare sparkline data
    const batteryData = telemetryData.length > 0
        ? telemetryData.map(t => ({ time: t.time, value: t.battery_voltage ?? 3.7 }))
        : generateMockData(3.7, 0.3, 24);

    const temperatureData = telemetryData.length > 0
        ? telemetryData.map(t => ({ time: t.time, value: t.temperature ?? -45 }))
        : generateMockData(-45, 5, 24);

    const pressureData = telemetryData.length > 0
        ? telemetryData.map(t => ({ time: t.time, value: t.pressure ?? 120 }))
        : generateMockData(120, 10, 24);

    const rssiData = telemetryData.length > 0
        ? telemetryData.map(t => ({ time: t.time, value: t.rssi ?? -112 }))
        : generateMockData(-112, 5, 24);
    // Prevent body scroll when sidebar is open
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'unset';
        }
        return () => {
            document.body.style.overflow = 'unset';
        };
    }, [isOpen]);

    return (
        <>
            {/* Backdrop overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30 transition-opacity duration-300"
                    onClick={onClose}
                />
            )}

            {/* Sidebar */}
            <div
                className={`fixed top-0 right-0 h-full w-[600px] bg-black/90 backdrop-blur-md border-l border-cyan-500/30 z-40 transform transition-transform duration-500 ease-in-out ${
                    isOpen ? 'translate-x-0' : 'translate-x-full'
                } flex flex-col shadow-2xl`}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-cyan-500/30">
                    <div>
                        <h2 className="text-2xl font-bold text-cyan-400">SYSTEM INTERNALS</h2>
                        <p className="text-gray-400 text-sm mt-1">Payload Diagnostics - {balloonId}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-white transition-colors p-2 hover:bg-white/10 rounded-lg"
                        aria-label="Close sidebar"
                    >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Content - Scrollable */}
                <div className="flex-1 overflow-y-auto">
                    {/* 3D PCB Viewer */}
                    <div className="p-6 border-b border-cyan-500/20">
                        <h3 className="text-cyan-400 text-sm uppercase tracking-wider mb-4">PCB 3D Model</h3>
                        <div className="h-64 bg-black/40 rounded-lg border border-cyan-500/20 overflow-hidden">
                            <Payload3DViewer />
                        </div>
                    </div>

                    {/* Mission Log */}
                    <div className="p-6 border-b border-cyan-500/20">
                        <h3 className="text-cyan-400 text-sm uppercase tracking-wider mb-4">Mission Log</h3>
                        <div className="bg-black/40 rounded-lg border border-cyan-500/20 p-4 font-mono text-xs text-gray-300 h-48 overflow-y-auto">
                            <div className="space-y-2">
                                <div className="text-cyan-400/60">[2026-01-23 02:45:12 UTC]</div>
                                <div className="text-green-400">SYSTEM INIT: All subsystems nominal</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:45:15 UTC]</div>
                                <div className="text-green-400">LORAWAN: Connected to TTN network</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:45:18 UTC]</div>
                                <div className="text-green-400">GNSS: GPS lock acquired (12 satellites)</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:45:20 UTC]</div>
                                <div className="text-yellow-400">POWER: Battery at 3.7V (85% capacity)</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:45:25 UTC]</div>
                                <div className="text-green-400">TELEMETRY: First packet transmitted</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:46:00 UTC]</div>
                                <div className="text-green-400">ALTITUDE: 15,000m reached</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:47:30 UTC]</div>
                                <div className="text-blue-400">WIND: Detected crosswind pattern</div>
                                
                                <div className="text-cyan-400/60">[2026-01-23 02:48:00 UTC]</div>
                                <div className="text-green-400">STATUS: All systems operational</div>
                            </div>
                        </div>
                    </div>

                    {/* Science Telemetry with Sparklines */}
                    <div className="p-6">
                        <h3 className="text-cyan-400 text-sm uppercase tracking-wider mb-4">Science Telemetry</h3>
                        <div className="bg-black/40 rounded-lg border border-cyan-500/20 p-4 space-y-4">
                            {/* Power System */}
                            <div>
                                <div className="text-cyan-400/60 text-xs uppercase tracking-wider mb-2">POWER SYSTEM</div>
                                <MetricSparkline
                                    data={batteryData}
                                    dataKey="battery_voltage"
                                    color="#00ffff"
                                    currentValue={latestTelemetry.battery_voltage ?? 3.72}
                                    unit="V"
                                />
                            </div>

                            {/* Environmental */}
                            <div>
                                <div className="text-cyan-400/60 text-xs uppercase tracking-wider mb-2">ENVIRONMENTAL</div>
                                <div className="space-y-3">
                                    <MetricSparkline
                                        data={temperatureData}
                                        dataKey="temperature"
                                        color="#ff6b6b"
                                        currentValue={latestTelemetry.temperature ?? -45.2}
                                        unit="°C"
                                    />
                                    <MetricSparkline
                                        data={pressureData}
                                        dataKey="pressure"
                                        color="#4ecdc4"
                                        currentValue={latestTelemetry.pressure ?? 120.5}
                                        unit=" mbar"
                                    />
                                </div>
                            </div>

                            {/* Communications */}
                            <div>
                                <div className="text-cyan-400/60 text-xs uppercase tracking-wider mb-2">COMMUNICATIONS</div>
                                <MetricSparkline
                                    data={rssiData}
                                    dataKey="rssi"
                                    color="#ffd93d"
                                    currentValue={latestTelemetry.rssi ?? -112}
                                    unit=" dBm"
                                />
                            </div>

                            {/* Static Navigation Data */}
                            <div>
                                <div className="text-cyan-400/60 text-xs uppercase tracking-wider mb-2">NAVIGATION</div>
                                <div className="space-y-1 text-gray-300 font-mono text-xs">
                                    <div>GPS Sats: 12</div>
                                    <div>HDOP: 1.2</div>
                                    <div>Speed: 45.2 m/s</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
