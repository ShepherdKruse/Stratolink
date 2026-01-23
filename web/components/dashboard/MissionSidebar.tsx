'use client';

import { useEffect } from 'react';
import Payload3DViewer from './Payload3DViewer';
import MetricSparkline from './MetricSparkline';

import MissionTimeline from './MissionTimeline';

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
    timelineProps?: {
        startTime: Date;
        endTime: Date;
        currentTime: Date;
        onChange: (timestamp: Date) => void;
    } | null;
}

export default function MissionSidebar({ isOpen, onClose, balloonId, telemetryData = [], timelineProps }: MissionSidebarProps) {
    // Generate mock data if no telemetry data provided
    const generateMockData = (baseValue: number, variance: number, count: number = 24) => {
        const now = new Date();
        return Array.from({ length: count }, (_, i) => {
            const time = new Date(now.getTime() - (count - i) * 60 * 60 * 1000);
            const value = baseValue + (Math.random() - 0.5) * variance;
            return { time, value: Math.max(0, value) };
        });
    };

    const latestTelemetry = telemetryData.length > 0 
        ? telemetryData[telemetryData.length - 1]
        : { battery_voltage: 3.72, temperature: -45.2, pressure: 120.5, rssi: -112 };

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

    // System log entries - exposed inner workings
    const systemLogs = [
        { time: '02:48:12.847', level: 'info', msg: 'Telemetry packet TX complete, seq=1847' },
        { time: '02:48:00.123', level: 'info', msg: 'GPS fix acquired: 12 sats, HDOP=1.2' },
        { time: '02:47:45.892', level: 'warn', msg: 'Battery voltage below 3.8V threshold' },
        { time: '02:47:30.456', level: 'info', msg: 'LoRaWAN uplink SF7BW125, freq=903.9MHz' },
        { time: '02:47:15.234', level: 'info', msg: 'Sensor read: T=-45.2°C, P=120.5mbar' },
        { time: '02:47:00.001', level: 'info', msg: 'Sleep cycle exit, runtime 847ms' },
        { time: '02:46:45.789', level: 'info', msg: 'ADC calibration complete' },
        { time: '02:46:30.567', level: 'info', msg: 'Power mode: ACTIVE, V_bat=3.72V' },
        { time: '02:46:15.345', level: 'info', msg: 'Entering TX window slot 3' },
        { time: '02:46:00.123', level: 'info', msg: 'GNSS cold start, searching...' },
    ];

    return (
        <>
            {/* Backdrop - Desktop only (mobile bottom sheet doesn't need backdrop) */}
            {isOpen && (
                <div
                    className="hidden md:block fixed inset-0 bg-black/60 z-30"
                    onClick={onClose}
                />
            )}

            {/* Sidebar - Mobile: Bottom Sheet, Desktop: Side Panel */}
            <div
                className={`fixed bottom-0 left-0 w-full h-[50vh] z-40 bg-[#1a1a1a] border-t border-[#333] rounded-t-3xl transform transition-transform duration-300 flex flex-col
                    md:fixed md:right-0 md:top-0 md:bottom-auto md:left-auto md:w-[520px] md:h-full md:rounded-t-none md:rounded-l-3xl md:border-t-0 md:border-l ${
                    isOpen 
                        ? 'translate-y-0 md:translate-y-0 md:translate-x-0' 
                        : 'translate-y-full md:translate-y-0 md:translate-x-full'
                    }`}
            >
                {/* Drag Handle - Mobile Only */}
                <div className="md:hidden flex justify-center pt-2 pb-1">
                    <div className="w-12 h-1 bg-[#333] rounded-full" />
                </div>

                {/* Header - compact */}
                <div className="flex items-center justify-between p-3 border-b border-[#333]">
                    <div>
                        <div className="flex items-baseline gap-2">
                            <span className="text-[13px] font-semibold text-[#e5e5e5]">Device Internals</span>
                            <span className="font-mono text-[11px] text-[#4a90d9]">{balloonId}</span>
                        </div>
                        <p className="text-[10px] text-[#666] mt-0.5 font-mono">
                            {telemetryData.length} telemetry points loaded
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-[#666] hover:text-[#e5e5e5] transition-colors p-1 border border-[#333] hover:border-[#666]"
                        aria-label="Close sidebar"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Mission Timeline - Mobile Only (inside sidebar) */}
                {timelineProps && (
                    <div className="md:hidden border-b border-[#333]">
                        <MissionTimeline
                            startTime={timelineProps.startTime}
                            endTime={timelineProps.endTime}
                            currentTime={timelineProps.currentTime}
                            onChange={timelineProps.onChange}
                        />
                    </div>
                )}

                {/* Content - Scrollable */}
                <div className="flex-1 overflow-y-auto">
                    {/* Two-column layout for density - Desktop, Single column on mobile */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-[#333]">
                        {/* Left Column: 3D View + Telemetry */}
                        <div className="bg-[#1a1a1a]">
                            {/* PCB 3D Viewer */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Hardware Model</div>
                                <div className="h-40 bg-[#141414] border border-[#333]">
                                    <Payload3DViewer />
                                </div>
                            </div>

                            {/* Power Telemetry */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Power System</div>
                                <MetricSparkline
                                    data={batteryData}
                                    dataKey="V_bat"
                                    color="#4a90d9"
                                    currentValue={latestTelemetry.battery_voltage ?? 3.72}
                                    unit="V"
                                />
                            </div>

                            {/* Environmental */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Environment</div>
                                <div className="space-y-3">
                                    <MetricSparkline
                                        data={temperatureData}
                                        dataKey="temp"
                                        color="#c44"
                                        currentValue={latestTelemetry.temperature ?? -45.2}
                                        unit="°C"
                                    />
                                    <MetricSparkline
                                        data={pressureData}
                                        dataKey="pres"
                                        color="#4a9"
                                        currentValue={latestTelemetry.pressure ?? 120.5}
                                        unit="mbar"
                                    />
                                </div>
                            </div>

                            {/* RF */}
                            <div className="p-3">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">RF Link</div>
                                <MetricSparkline
                                    data={rssiData}
                                    dataKey="rssi"
                                    color="#b84"
                                    currentValue={latestTelemetry.rssi ?? -112}
                                    unit="dBm"
                                />
                            </div>
                        </div>

                        {/* Right Column: System State + Logs */}
                        <div className="bg-[#1a1a1a]">
                            {/* Raw State Dump */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">System State</div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>device_id</span>
                                        <span className="text-[#e5e5e5]">{balloonId}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>firmware</span>
                                        <span className="text-[#e5e5e5]">v2.1.4</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>uptime_s</span>
                                        <span className="text-[#e5e5e5]">847293</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>tx_count</span>
                                        <span className="text-[#e5e5e5]">1847</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>gps_sats</span>
                                        <span className="text-[#e5e5e5]">12</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>hdop</span>
                                        <span className="text-[#e5e5e5]">1.2</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>sf</span>
                                        <span className="text-[#e5e5e5]">SF7BW125</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>freq_mhz</span>
                                        <span className="text-[#e5e5e5]">903.9</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>power_mode</span>
                                        <span className="text-[#4a9]">ACTIVE</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>sleep_ms</span>
                                        <span className="text-[#e5e5e5]">60000</span>
                                    </div>
                                </div>
                            </div>

                            {/* Navigation Data */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Navigation</div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>ground_speed</span>
                                        <span className="text-[#e5e5e5]">45.2 m/s</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>track_deg</span>
                                        <span className="text-[#e5e5e5]">087.4°</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>climb_rate</span>
                                        <span className="text-[#e5e5e5]">+2.1 m/s</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>dist_traveled</span>
                                        <span className="text-[#e5e5e5]">847.3 km</span>
                                    </div>
                                </div>
                            </div>

                            {/* System Log - exposed inner workings */}
                            <div className="p-3">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">System Log</div>
                                <div className="bg-[#141414] border border-[#333] p-2 h-[200px] overflow-y-auto font-mono text-[9px]">
                                    {systemLogs.map((log, i) => (
                                        <div key={i} className="flex gap-2 py-0.5">
                                            <span className="text-[#666] shrink-0">{log.time}</span>
                                            <span className={`shrink-0 w-10 ${
                                                log.level === 'warn' ? 'text-[#b84]' : 
                                                log.level === 'error' ? 'text-[#c44]' : 'text-[#666]'
                                            }`}>
                                                [{log.level.toUpperCase()}]
                                            </span>
                                            <span className="text-[#999]">{log.msg}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer - raw data access */}
                <div className="p-2 border-t border-[#333] bg-[#141414]">
                    <div className="flex items-center justify-between text-[9px] font-mono text-[#666]">
                        <span>Updated: {new Date().toISOString().substring(11, 23)} UTC</span>
                        <div className="flex gap-2">
                            <button className="hover:text-[#999] transition-colors">[Export JSON]</button>
                            <button className="hover:text-[#999] transition-colors">[Export CSV]</button>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
