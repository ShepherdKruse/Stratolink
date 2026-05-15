'use client';

import type { ReactNode } from 'react';
import { useEffect } from 'react';
import Payload3DViewer from './Payload3DViewer';
import MetricSparkline from './MetricSparkline';

import MissionTimeline from './MissionTimeline';

interface MissionSidebarTelemetry {
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
}

interface MissionSidebarProps {
    isOpen: boolean;
    onClose: () => void;
    balloonId: string;
    launcherName?: string;
    telemetryData?: MissionSidebarTelemetry[];
    timelineProps?: {
        startTime: Date;
        endTime: Date;
        currentTime: Date;
        onChange: (timestamp: Date) => void;
    } | null;
}

/** Render a value or an em-dash when undefined/null. */
function v(x: unknown, suffix: string = '', dashColor = 'text-[#555]'): ReactNode {
    if (x === undefined || x === null || (typeof x === 'number' && !Number.isFinite(x))) {
        return <span className={dashColor}>—</span>;
    }
    return <>{x}{suffix}</>;
}

/** Format uptime seconds as a human-friendly Hh Mm Ss string. */
function formatUptime(secs: number | undefined): string {
    if (secs === undefined || secs === null || !Number.isFinite(secs)) return '—';
    const s = Math.trunc(secs);
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    const seconds = s % 60;
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
}

/** "SF7BW125" style LoRa descriptor from SF + bandwidth (Hz). */
function formatLoraConfig(sf: number | undefined, bw: number | undefined): string | undefined {
    if (sf === undefined && bw === undefined) return undefined;
    const sfPart = sf !== undefined ? `SF${sf}` : 'SF?';
    const bwPart = bw !== undefined ? `BW${Math.round(bw / 1000)}` : '';
    return `${sfPart}${bwPart}`;
}

export default function MissionSidebar({ isOpen, onClose, balloonId, launcherName, telemetryData = [], timelineProps }: MissionSidebarProps) {
    /* Latest row is the source of truth for every "current value" readout.
     * Sparkline series filter out null/undefined samples so a single bad row
     * doesn't render a gap as zero. */
    const latestTelemetry: Partial<MissionSidebarTelemetry> = telemetryData.length > 0
        ? telemetryData[telemetryData.length - 1]
        : {};

    const seriesFor = (selector: (t: MissionSidebarTelemetry) => number | undefined) =>
        telemetryData
            .map(t => ({ time: t.time, raw: selector(t) }))
            .filter(p => typeof p.raw === 'number' && Number.isFinite(p.raw))
            .map(p => ({ time: p.time, value: p.raw as number }));

    const batteryData = seriesFor(t => t.battery_voltage);
    const temperatureData = seriesFor(t => t.temperature);
    const pressureData = seriesFor(t => t.pressure);
    const rssiData = seriesFor(t => t.rssi);

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

    /* Synthesise a short, real system log from recent telemetry rows. We
     * surface the most recent few packets with key derived facts so the
     * panel still has the "exposed inner workings" feel — but everything
     * is grounded in real data. */
    const systemLogs = telemetryData
        .slice(-10)
        .reverse()
        .map((t, idx) => {
            const ts = (t.time instanceof Date ? t.time : new Date(t.time)).toISOString().substring(11, 23);
            const parts: string[] = [];
            if (t.tx_count !== undefined) parts.push(`seq=${t.tx_count}`);
            if (t.gps_satellites !== undefined) parts.push(`sats=${t.gps_satellites}`);
            if (t.hdop !== undefined) parts.push(`hdop=${t.hdop.toFixed(1)}`);
            if (t.battery_voltage !== undefined) parts.push(`vbat=${t.battery_voltage.toFixed(2)}V`);
            if (t.rssi !== undefined) parts.push(`rssi=${t.rssi}dBm`);
            if (t.power_mode) parts.push(`mode=${t.power_mode}`);
            const level = (t.battery_voltage !== undefined && t.battery_voltage < 3.5) ? 'warn'
                : (t.acoustic_event && t.acoustic_event > 0) ? 'warn'
                : 'info';
            const msg = parts.length > 0
                ? `Telemetry RX ${parts.join(', ')}`
                : `Telemetry RX (packet ${idx + 1})`;
            return { time: ts, level, msg };
        });
    if (systemLogs.length === 0) {
        systemLogs.push({ time: '--:--:--', level: 'info', msg: 'No telemetry received yet' });
    }

    const lora = formatLoraConfig(latestTelemetry.lora_sf, latestTelemetry.lora_bw);
    const freqMhz = latestTelemetry.frequency_hz !== undefined
        ? (latestTelemetry.frequency_hz / 1e6).toFixed(3)
        : undefined;
    const lastPacketTs = telemetryData.length > 0
        ? (telemetryData[telemetryData.length - 1].time instanceof Date
            ? (telemetryData[telemetryData.length - 1].time as Date)
            : new Date(telemetryData[telemetryData.length - 1].time as string))
        : null;
    const lastPacketLabel = lastPacketTs ? lastPacketTs.toISOString().replace('T', ' ').substring(0, 19) + ' UTC' : '—';

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
                            {launcherName && `Launched by: ${launcherName} • `}
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

                            {/* Power System — real V_bat over the last 24h.
                              * Sparkline renders empty when the firmware hasn't
                              * sent any battery reading yet. */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Power System</div>
                                <MetricSparkline
                                    data={batteryData}
                                    dataKey="V_bat"
                                    color="#4a90d9"
                                    currentValue={latestTelemetry.battery_voltage ?? 0}
                                    unit={latestTelemetry.battery_voltage !== undefined ? 'V' : ' —'}
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
                                        currentValue={latestTelemetry.temperature ?? 0}
                                        unit={latestTelemetry.temperature !== undefined ? '°C' : ' —'}
                                    />
                                    <MetricSparkline
                                        data={pressureData}
                                        dataKey="pres"
                                        color="#4a9"
                                        currentValue={latestTelemetry.pressure ?? 0}
                                        unit={latestTelemetry.pressure !== undefined ? 'mbar' : ' —'}
                                    />
                                </div>
                            </div>

                            {/* RF signal trend */}
                            <div className="p-3">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">RF Signal</div>
                                <MetricSparkline
                                    data={rssiData}
                                    dataKey="rssi"
                                    color="#b84"
                                    currentValue={latestTelemetry.rssi ?? 0}
                                    unit={latestTelemetry.rssi !== undefined ? 'dBm' : ' —'}
                                />
                            </div>
                        </div>

                        {/* Right Column: System State + Logs */}
                        <div className="bg-[#1a1a1a]">
                            {/* Real System State — pulled from the latest telemetry row.
                              * Fields the firmware doesn't yet emit render as "—" so the
                              * gap is obvious without breaking the layout. */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider">System State</div>
                                    <div className="text-[9px] font-mono text-[#555]">{telemetryData.length} pkts</div>
                                </div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>device_id</span>
                                        <span className="text-[#e5e5e5]">{balloonId}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>last_packet</span>
                                        <span className="text-[#e5e5e5]">{lastPacketLabel}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>firmware</span>
                                        <span className="text-[#e5e5e5]">{v(latestTelemetry.firmware_version)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>uptime</span>
                                        <span className="text-[#e5e5e5]">{formatUptime(latestTelemetry.uptime_s)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>tx_count</span>
                                        <span className="text-[#e5e5e5]">{v(latestTelemetry.tx_count)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>power_mode</span>
                                        <span className={latestTelemetry.power_mode === 'ACTIVE' ? 'text-[#4a9]' : 'text-[#e5e5e5]'}>
                                            {v(latestTelemetry.power_mode)}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>sleep_ms</span>
                                        <span className="text-[#e5e5e5]">{v(latestTelemetry.sleep_ms)}</span>
                                    </div>
                                </div>
                            </div>

                            {/* GPS — fully real. lat/lon may be null when the firmware is in
                              * NOGPS power tier, so render an inline status badge in that case. */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider">GPS</div>
                                    {latestTelemetry.lat === undefined && (
                                        <span className="text-[9px] font-mono text-yellow-400">NO FIX</span>
                                    )}
                                </div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>lat</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.lat !== undefined ? latestTelemetry.lat.toFixed(6) + '°' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>lon</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.lon !== undefined ? latestTelemetry.lon.toFixed(6) + '°' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>alt</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.altitude_m !== undefined ? latestTelemetry.altitude_m.toLocaleString() + ' m' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>sats</span>
                                        <span className="text-[#e5e5e5]">{v(latestTelemetry.gps_satellites)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>hdop</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.hdop !== undefined ? latestTelemetry.hdop.toFixed(1) : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>ground_spd</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.gps_speed !== undefined ? latestTelemetry.gps_speed.toFixed(2) + ' m/s' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>heading</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.gps_heading !== undefined ? latestTelemetry.gps_heading.toFixed(1) + '°' : v(undefined)}</span>
                                    </div>
                                </div>
                            </div>

                            {/* LoRa link — sourced from TTN settings so always real when
                              * a packet has been received in the current session. */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">LoRa Link</div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>data_rate</span>
                                        <span className="text-[#e5e5e5]">{v(lora)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>freq_mhz</span>
                                        <span className="text-[#e5e5e5]">{v(freqMhz)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>rssi</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.rssi !== undefined ? latestTelemetry.rssi + ' dBm' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>snr</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.snr !== undefined ? latestTelemetry.snr.toFixed(1) + ' dB' : v(undefined)}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Sensors — all real, from the latest payload row. */}
                            <div className="p-3 border-b border-[#333]">
                                <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">Sensors</div>
                                <div className="font-mono text-[10px] space-y-1 text-[#999]">
                                    <div className="flex justify-between">
                                        <span>uv_index</span>
                                        <span className="text-[#e5e5e5]">{v(latestTelemetry.uv_index)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>ambient_lux</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.ambient_lux !== undefined ? `${latestTelemetry.ambient_lux} lux` : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>acoustic</span>
                                        {latestTelemetry.acoustic_event === undefined ? (
                                            <span className="text-[#555]">—</span>
                                        ) : (
                                            <span className={latestTelemetry.acoustic_event ? 'text-[#c44]' : 'text-[#4a9]'}>
                                                {latestTelemetry.acoustic_event ? 'EVENT' : 'quiet'}
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex justify-between">
                                        <span>accel_x</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_x !== undefined ? latestTelemetry.mems_accel_x.toFixed(2) + ' m/s²' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>accel_y</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_y !== undefined ? latestTelemetry.mems_accel_y.toFixed(2) + ' m/s²' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>accel_z</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.mems_accel_z !== undefined ? latestTelemetry.mems_accel_z.toFixed(2) + ' m/s²' : v(undefined)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>solar_mv</span>
                                        <span className="text-[#e5e5e5]">{latestTelemetry.solar_voltage !== undefined ? `${Math.round(latestTelemetry.solar_voltage * 1000)} mV` : v(undefined)}</span>
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
