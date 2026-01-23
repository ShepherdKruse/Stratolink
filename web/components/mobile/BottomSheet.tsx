'use client';

import { useState, useEffect } from 'react';
import { motion, PanInfo, useMotionValue, useTransform } from 'framer-motion';
import Payload3DViewer from '../dashboard/Payload3DViewer';
import MetricSparkline from '../dashboard/MetricSparkline';

interface BottomSheetProps {
    isOpen: boolean;
    onClose: () => void;
    balloonId: string;
    balloonData?: {
        altitude_m: number;
        lat: number;
        lon: number;
        battery_voltage?: number;
        velocity_heading?: number;
    };
    telemetryData?: Array<{
        time: Date | string;
        battery_voltage?: number;
        temperature?: number;
        pressure?: number;
        rssi?: number;
    }>;
}

export default function BottomSheet({ 
    isOpen, 
    onClose, 
    balloonId, 
    balloonData,
    telemetryData = [] 
}: BottomSheetProps) {
    const [sheetHeight, setSheetHeight] = useState(800);
    const [isExpanded, setIsExpanded] = useState(false);
    
    useEffect(() => {
        setSheetHeight(window.innerHeight);
        const handleResize = () => setSheetHeight(window.innerHeight);
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    const PEEK_HEIGHT = sheetHeight * 0.25; // 25% peek
    const EXPANDED_HEIGHT = sheetHeight * 0.9; // 90% expanded
    
    const y = useMotionValue(isExpanded ? 0 : sheetHeight - PEEK_HEIGHT);

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

    // Reset state when sheet opens/closes
    useEffect(() => {
        if (isOpen) {
            setIsExpanded(false);
            y.set(sheetHeight - PEEK_HEIGHT);
        } else {
            y.set(sheetHeight);
        }
    }, [isOpen, y, sheetHeight, PEEK_HEIGHT]);

    const handleDragEnd = (_event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
        const velocity = info.velocity.y;

        // Fast swipe down closes
        if (velocity > 500) {
            onClose();
            return;
        }

        // Fast swipe up expands
        if (velocity < -500) {
            setIsExpanded(true);
            y.set(0);
            return;
        }

        // Slow drag: snap to nearest position
        const currentY = y.get();
        const midPoint = sheetHeight - (PEEK_HEIGHT + EXPANDED_HEIGHT) / 2;

        if (currentY < midPoint) {
            setIsExpanded(true);
            y.set(0);
        } else {
            setIsExpanded(false);
            y.set(sheetHeight - PEEK_HEIGHT);
        }
    };

    const opacity = useTransform(y, [0, SHEET_HEIGHT - PEEK_HEIGHT], [1, 0.3]);

    if (!isOpen) return null;

    const altitudeFt = balloonData?.altitude_m ? balloonData.altitude_m * 3.28084 : 0;
    const isAlive = balloonData && balloonData.altitude_m > 100;

    return (
        <>
            {/* Backdrop */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: isOpen ? 0.6 : 0 }}
                exit={{ opacity: 0 }}
                onClick={onClose}
                className="fixed inset-0 bg-black z-40"
            />

            {/* Bottom Sheet */}
            <motion.div
                drag="y"
                dragConstraints={{ top: 0, bottom: sheetHeight - PEEK_HEIGHT }}
                dragElastic={0.2}
                onDragEnd={handleDragEnd}
                animate={{
                    y: isExpanded ? 0 : sheetHeight - PEEK_HEIGHT,
                }}
                transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                style={{ y }}
                className="fixed left-0 right-0 z-50 bg-[#1a1a1a] border-t border-[#333] rounded-t-3xl shadow-2xl"
            >
                {/* Drag Handle */}
                <div className="flex justify-center pt-3 pb-2">
                    <div className="w-12 h-1.5 bg-[#333] rounded-full" />
                </div>

                {/* Stage 1: Glance View (Always Visible) */}
                <motion.div style={{ opacity }} className="px-4 pb-4 border-b border-[#333]">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            {/* Status Dot */}
                            <div className={`w-4 h-4 rounded-full ${isAlive ? 'bg-[#4a9] animate-pulse' : 'bg-[#666]'}`} />
                            <div>
                                <div className="font-mono text-[12px] text-[#4a90d9] font-semibold">{balloonId}</div>
                                <div className="font-mono text-[20px] text-[#e5e5e5] font-bold">
                                    {altitudeFt > 0 ? `${(altitudeFt / 1000).toFixed(1)}k ft` : '—'}
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={() => {
                                // Ping action - request immediate update
                            }}
                            className="bg-[#4a90d9]/20 border border-[#4a90d9] text-[#4a90d9] px-4 py-2 rounded-lg text-[12px] font-mono min-h-[44px]"
                        >
                            Ping
                        </button>
                    </div>
                </motion.div>

                {/* Stage 2: Deep Dive (Scrollable when expanded) */}
                <div className="overflow-y-auto" style={{ height: isExpanded ? EXPANDED_HEIGHT - 100 : 0 }}>
                    <div className="p-4 space-y-4">
                        {/* 3D PCB Render */}
                        <div>
                            <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Hardware Model</div>
                            <div className="h-48 bg-[#141414] border border-[#333] rounded">
                                <Payload3DViewer />
                            </div>
                        </div>

                        {/* Sparklines - Vertical Stack */}
                        <div className="space-y-4">
                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Power System</div>
                                <MetricSparkline
                                    data={batteryData}
                                    dataKey="V_bat"
                                    color="#4a90d9"
                                    currentValue={latestTelemetry.battery_voltage ?? 3.72}
                                    unit="V"
                                />
                            </div>

                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Temperature</div>
                                <MetricSparkline
                                    data={temperatureData}
                                    dataKey="temp"
                                    color="#c44"
                                    currentValue={latestTelemetry.temperature ?? -45.2}
                                    unit="°C"
                                />
                            </div>

                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Pressure</div>
                                <MetricSparkline
                                    data={pressureData}
                                    dataKey="pres"
                                    color="#4a9"
                                    currentValue={latestTelemetry.pressure ?? 120.5}
                                    unit="mbar"
                                />
                            </div>

                            <div>
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

                        {/* Health Grid - Large Tiles */}
                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Battery</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.battery_voltage?.toFixed(2) ?? '3.72'}V
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">
                                    {Math.min(100, Math.max(0, (((latestTelemetry.battery_voltage ?? 3.72) - 3.0) / (4.2 - 3.0)) * 100)).toFixed(0)}% capacity
                                </div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Solar</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">Active</div>
                                <div className="text-[10px] text-[#666] mt-1">Day cycle</div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Temp</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.temperature?.toFixed(1) ?? '-45.2'}°C
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">Stratosphere</div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Signal</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.rssi ?? -112} dBm
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">LoRaWAN</div>
                            </div>
                        </div>

                        {/* Path Timeline - Vertical List */}
                        <div>
                            <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-3">Flight Path</div>
                            <div className="space-y-2">
                                {[
                                    { time: '08:00 AM', event: 'Sunrise detected (Wake up)', status: 'success' },
                                    { time: '04:00 AM', event: 'Entered Jet Stream (110 mph)', status: 'info' },
                                    { time: '12:00 AM', event: 'Crossed Atlantic', status: 'info' },
                                    { time: '08:00 PM', event: 'Launch confirmed', status: 'success' },
                                ].map((entry, i) => (
                                    <div key={i} className="flex gap-3">
                                        <div className="flex flex-col items-center">
                                            <div className={`w-2 h-2 rounded-full ${entry.status === 'success' ? 'bg-[#4a9]' : 'bg-[#666]'}`} />
                                            {i < 3 && <div className="w-px h-8 bg-[#333] mt-1" />}
                                        </div>
                                        <div className="flex-1 pb-2">
                                            <div className="font-mono text-[10px] text-[#666]">{entry.time}</div>
                                            <div className="font-mono text-[11px] text-[#e5e5e5]">{entry.event}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </motion.div>
        </>
    );
}
