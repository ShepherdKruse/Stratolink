'use client';

import { ResponsiveContainer, LineChart, Line, Tooltip } from 'recharts';

interface MetricSparklineProps {
    data: Array<{ time: Date | string; value: number }>;
    dataKey: string;
    color: string;
    currentValue: number;
    unit?: string;
}

export default function MetricSparkline({ data, dataKey, color, currentValue, unit = '' }: MetricSparklineProps) {
    // Format data for Recharts (convert Date to timestamp if needed)
    const chartData = data.map(item => ({
        ...item,
        time: item.time instanceof Date ? item.time.getTime() : item.time,
        [dataKey]: item.value,
    }));

    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length) {
            const value = payload[0].value;
            const time = payload[0].payload.time;
            return (
                <div className="bg-black/90 border border-cyan-500/50 rounded px-2 py-1 text-xs font-mono">
                    <div className="text-cyan-400">{new Date(time).toLocaleTimeString()}</div>
                    <div className="text-white">{value.toFixed(2)}{unit}</div>
                </div>
            );
        }
        return null;
    };

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <span className="text-cyan-400/60 text-xs uppercase tracking-wider">{dataKey}</span>
                <span className="text-white text-sm font-mono font-bold">
                    {currentValue.toFixed(2)}{unit}
                </span>
            </div>
            <div className="h-[50px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                        <Line
                            type="monotone"
                            dataKey={dataKey}
                            stroke={color}
                            strokeWidth={2}
                            dot={false}
                            isAnimationActive={false}
                        />
                        <Tooltip content={<CustomTooltip />} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
