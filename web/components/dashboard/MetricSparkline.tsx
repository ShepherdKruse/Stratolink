'use client';

import { ResponsiveContainer, LineChart, Line, Tooltip, ReferenceLine } from 'recharts';

interface MetricSparklineProps {
    data: Array<{ time: Date | string; value: number }>;
    dataKey: string;
    color: string;
    currentValue: number;
    unit?: string;
}

export default function MetricSparkline({ data, dataKey, color, currentValue, unit = '' }: MetricSparklineProps) {
    // Format data for Recharts
    const chartData = data.map(item => ({
        ...item,
        time: item.time instanceof Date ? item.time.getTime() : new Date(item.time as string).getTime(),
        [dataKey]: item.value,
    }));

    // Calculate min/max/avg for context
    const values = data.map(d => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;

    // Tufte-style tooltip - minimal
    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length) {
            const value = payload[0].value;
            const time = payload[0].payload.time;
            return (
                <div className="bg-[#1a1a1a] border border-[#333] px-2 py-1 font-mono text-[9px]">
                    <div className="text-[#666]">{new Date(time).toISOString().substring(11, 19)}</div>
                    <div className="text-[#e5e5e5]">{value.toFixed(2)}{unit}</div>
                </div>
            );
        }
        return null;
    };

    return (
        <div>
            {/* Header row: label and current value */}
            <div className="flex items-baseline justify-between mb-1">
                <span className="text-[10px] font-mono text-[#999]">{dataKey}</span>
                <span className="text-[12px] font-mono text-[#e5e5e5] font-semibold">
                    {currentValue.toFixed(2)}<span className="text-[#666] text-[10px]">{unit}</span>
                </span>
            </div>
            
            {/* Sparkline - Tufte style: no axes, no gridlines, just data */}
            <div className="h-[32px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
                        {/* Reference line for average - subtle */}
                        <ReferenceLine y={avg} stroke="#333" strokeDasharray="2 2" />
                        <Line
                            type="monotone"
                            dataKey={dataKey}
                            stroke={color}
                            strokeWidth={1}
                            dot={false}
                            isAnimationActive={false}
                        />
                        <Tooltip content={<CustomTooltip />} />
                    </LineChart>
                </ResponsiveContainer>
            </div>

            {/* Footer row: min/max range - dense annotation */}
            <div className="flex items-baseline justify-between text-[8px] font-mono text-[#666] mt-0.5">
                <span>min: {min.toFixed(1)}</span>
                <span>avg: {avg.toFixed(1)}</span>
                <span>max: {max.toFixed(1)}</span>
            </div>
        </div>
    );
}
