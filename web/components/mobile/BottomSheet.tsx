'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
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
        launcher_name?: string;
    };
    telemetryData?: Array<{
        time: Date | string;
        battery_voltage?: number;
        solar_voltage?: number;
        temperature?: number;
        pressure?: number;
        rssi?: number;
        snr?: number;
        lat?: number;
        lon?: number;
        altitude_m?: number;
        gps_speed?: number;
        gps_heading?: number;
        gps_satellites?: number;
        uv_index?: number;
        ambient_lux?: number;
        acoustic_event?: number;
        mems_accel_x?: number;
        mems_accel_y?: number;
        mems_accel_z?: number;
        firmware_version?: string;
        uptime_s?: number;
        tx_count?: number;
        hdop?: number;
        power_mode?: string;
        sleep_ms?: number;
        lora_sf?: number;
        lora_bw?: number;
        frequency_hz?: number;
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
        if (typeof window !== 'undefined') {
            setSheetHeight(window.innerHeight);
            const handleResize = () => {
                if (typeof window !== 'undefined') {
                    setSheetHeight(window.innerHeight);
                }
            };
            window.addEventListener('resize', handleResize);
            return () => window.removeEventListener('resize', handleResize);
        }
    }, []);

    const PEEK_HEIGHT = sheetHeight * 0.25; // 25% peek
    const EXPANDED_HEIGHT = sheetHeight * 0.9; // 90% expanded

    const latestTelemetry: Partial<NonNullable<BottomSheetProps['telemetryData']>[number]> =
        telemetryData.length > 0 ? telemetryData[telemetryData.length - 1] : {};

    const seriesFor = (sel: (t: NonNullable<BottomSheetProps['telemetryData']>[number]) => number | undefined) =>
        telemetryData
            .map(t => ({ time: t.time, raw: sel(t) }))
            .filter(p => typeof p.raw === 'number' && Number.isFinite(p.raw))
            .map(p => ({ time: p.time, value: p.raw as number }));

    const batteryData = seriesFor(t => t.battery_voltage);
    const temperatureData = seriesFor(t => t.temperature);
    const pressureData = seriesFor(t => t.pressure);
    const rssiData = seriesFor(t => t.rssi);

    // Reset state when sheet opens/closes
    useEffect(() => {
        if (isOpen) {
            setIsExpanded(false);
        }
    }, [isOpen]);

    // Removed drag functionality - now uses button toggle only

    // Opacity based on expanded state
    const opacity = isExpanded ? 1 : 0.3;

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
                animate={{
                    y: isExpanded ? -(sheetHeight - EXPANDED_HEIGHT) : 0,
                }}
                transition={{ type: 'spring', damping: 40, stiffness: 400 }}
                style={{ 
                    maxHeight: `${EXPANDED_HEIGHT}px`, 
                    height: isExpanded ? `${EXPANDED_HEIGHT}px` : `${PEEK_HEIGHT}px` 
                }}
                className="fixed bottom-0 left-0 right-0 z-50 bg-[#1a1a1a] border-t border-[#333] rounded-t-3xl shadow-2xl"
            >
                {/* Header with Toggle Button */}
                <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-[#333]">
                    <div className="flex-1" />
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="flex items-center justify-center w-10 h-10 rounded-full bg-[#333] hover:bg-[#444] transition-colors"
                        aria-label={isExpanded ? "Collapse" : "Expand"}
                    >
                        {isExpanded ? (
                            <svg className="w-5 h-5 text-[#999]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                        ) : (
                            <svg className="w-5 h-5 text-[#999]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                            </svg>
                        )}
                    </button>
                    <button
                        onClick={onClose}
                        className="flex items-center justify-center w-10 h-10 rounded-full bg-[#333] hover:bg-[#c44] transition-colors ml-2"
                        aria-label="Close"
                    >
                        <svg className="w-5 h-5 text-[#999] hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Stage 1: Glance View (Always Visible) */}
                <div style={{ opacity }} className="px-4 pb-4 border-b border-[#333]">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            {/* Status Dot */}
                            <div className={`w-4 h-4 rounded-full ${isAlive ? 'bg-[#4a9] animate-pulse' : 'bg-[#666]'}`} />
                            <div>
                                <div className="font-mono text-[12px] text-[#4a90d9] font-semibold">{balloonId}</div>
                                <div className="font-mono text-[20px] text-[#e5e5e5] font-bold">
                                    {altitudeFt > 0 ? `${(altitudeFt / 1000).toFixed(1)}k ft` : '—'}
                                </div>
                                {balloonData?.launcher_name && (
                                    <div className="font-mono text-[9px] text-[#666] mt-0.5">
                                        {balloonData.launcher_name}
                                    </div>
                                )}
                            </div>
                        </div>
                        <button
                            onClick={() => {
                                // Ping action - request immediate update
                                // In a real implementation, this would trigger a refresh of telemetry data
                                console.log('Ping requested for', balloonId);
                                // Could trigger a refetch or send a command to the device
                            }}
                            className="bg-[#4a90d9]/20 border border-[#4a90d9] text-[#4a90d9] px-4 py-2 rounded-lg text-[12px] font-mono min-h-[44px] active:bg-[#4a90d9]/30 transition-colors"
                        >
                            Ping
                        </button>
                    </div>
                </div>

                {/* Stage 2: Deep Dive (Scrollable when expanded) */}
                <div className="overflow-y-auto" style={{ height: isExpanded ? `${EXPANDED_HEIGHT - PEEK_HEIGHT - 20}px` : '0px' }}>
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
                                    currentValue={latestTelemetry.battery_voltage ?? 0}
                                    unit={latestTelemetry.battery_voltage !== undefined ? 'V' : ' —'}
                                />
                            </div>

                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Temperature</div>
                                <MetricSparkline
                                    data={temperatureData}
                                    dataKey="temp"
                                    color="#c44"
                                    currentValue={latestTelemetry.temperature ?? 0}
                                    unit={latestTelemetry.temperature !== undefined ? '°C' : ' —'}
                                />
                            </div>

                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Pressure</div>
                                <MetricSparkline
                                    data={pressureData}
                                    dataKey="pres"
                                    color="#4a9"
                                    currentValue={latestTelemetry.pressure ?? 0}
                                    unit={latestTelemetry.pressure !== undefined ? 'mbar' : ' —'}
                                />
                            </div>

                            <div>
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">RF Link</div>
                                <MetricSparkline
                                    data={rssiData}
                                    dataKey="rssi"
                                    color="#b84"
                                    currentValue={latestTelemetry.rssi ?? 0}
                                    unit={latestTelemetry.rssi !== undefined ? 'dBm' : ' —'}
                                />
                            </div>
                        </div>

                        {/* Health Grid — values pulled from the latest telemetry row.
                          * Each tile shows "—" when the firmware hasn't reported that field. */}
                        <div className="grid grid-cols-2 gap-3">
                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Battery</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.battery_voltage !== undefined ? `${latestTelemetry.battery_voltage.toFixed(2)}V` : '—'}
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">
                                    {latestTelemetry.battery_voltage !== undefined
                                        ? `${Math.min(100, Math.max(0, ((latestTelemetry.battery_voltage - 3.0) / (4.2 - 3.0)) * 100)).toFixed(0)}% capacity`
                                        : 'no data'}
                                </div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Solar</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.solar_voltage !== undefined ? `${Math.round(latestTelemetry.solar_voltage * 1000)} mV` : '—'}
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">
                                    {latestTelemetry.solar_voltage !== undefined && latestTelemetry.solar_voltage > 0.5 ? 'charging' : 'idle'}
                                </div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Temp</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.temperature !== undefined ? `${latestTelemetry.temperature.toFixed(1)}°C` : '—'}
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">{latestTelemetry.pressure !== undefined ? `${latestTelemetry.pressure.toFixed(1)} mbar` : 'pressure: —'}</div>
                            </div>

                            <div className="bg-[#141414] border border-[#333] p-4 rounded">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Signal</div>
                                <div className="font-mono text-[18px] text-[#e5e5e5] font-bold">
                                    {latestTelemetry.rssi !== undefined ? `${Math.round(latestTelemetry.rssi)} dBm` : '—'}
                                </div>
                                <div className="text-[10px] text-[#666] mt-1">
                                    {latestTelemetry.snr !== undefined ? `SNR ${latestTelemetry.snr.toFixed(1)} dB` : 'snr: —'}
                                </div>
                            </div>
                        </div>

                        {/* Sensors */}
                        <div className="bg-[#141414] border border-[#333] p-4 rounded">
                            <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Sensors</div>
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-[#999]">
                                <div className="flex justify-between"><span>uv_index</span><span className="text-[#e5e5e5]">{latestTelemetry.uv_index ?? '—'}</span></div>
                                <div className="flex justify-between"><span>lux</span><span className="text-[#e5e5e5]">{latestTelemetry.ambient_lux ?? '—'}</span></div>
                                <div className="flex justify-between"><span>acoustic</span><span className={latestTelemetry.acoustic_event ? 'text-[#c44]' : 'text-[#e5e5e5]'}>{latestTelemetry.acoustic_event === undefined ? '—' : latestTelemetry.acoustic_event ? 'event' : 'quiet'}</span></div>
                                <div className="flex justify-between"><span>sats</span><span className="text-[#e5e5e5]">{latestTelemetry.gps_satellites ?? '—'}</span></div>
                                <div className="flex justify-between"><span>accel_x</span><span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_x !== undefined ? latestTelemetry.mems_accel_x.toFixed(2) : '—'}</span></div>
                                <div className="flex justify-between"><span>accel_y</span><span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_y !== undefined ? latestTelemetry.mems_accel_y.toFixed(2) : '—'}</span></div>
                                <div className="flex justify-between"><span>accel_z</span><span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_z !== undefined ? latestTelemetry.mems_accel_z.toFixed(2) : '—'}</span></div>
                                <div className="flex justify-between"><span>fw</span><span className="text-[#e5e5e5]">{latestTelemetry.firmware_version ?? '—'}</span></div>
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
