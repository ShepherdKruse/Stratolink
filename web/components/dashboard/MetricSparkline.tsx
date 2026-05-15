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
    const chartData = data.map(item => ({
        ...item,
        time: item.time instanceof Date ? item.time.getTime() : new Date(item.time as string).getTime(),
        [dataKey]: item.value,
    }));

    /* When the device hasn't reported this metric yet, `data` is empty and
     * naive Math.min/max would produce ±Infinity. Bail out to a placeholder
     * row so the panel still renders cleanly. */
    const hasData = data.length > 0;
    const values = data.map(d => d.value);
    const min = hasData ? Math.min(...values) : 0;
    const max = hasData ? Math.max(...values) : 0;
    const avg = hasData ? values.reduce((a, b) => a + b, 0) / values.length : 0;

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
            <div className="flex items-baseline justify-between mb-1">
                <span className="text-[10px] font-mono text-[#999]">{dataKey}</span>
                <span className="text-[12px] font-mono text-[#e5e5e5] font-semibold">
                    {hasData ? currentValue.toFixed(2) : '—'}
                    <span className="text-[#666] text-[10px]">{hasData ? unit : ''}</span>
                </span>
            </div>

            <div className="h-[32px] w-full">
                {hasData ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
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
                ) : (
                    <div className="h-full flex items-center justify-center text-[9px] font-mono text-[#444]">
                        awaiting data
                    </div>
                )}
            </div>

            <div className="flex items-baseline justify-between text-[8px] font-mono text-[#666] mt-0.5">
                <span>min: {hasData ? min.toFixed(1) : '—'}</span>
                <span>avg: {hasData ? avg.toFixed(1) : '—'}</span>
                <span>max: {hasData ? max.toFixed(1) : '—'}</span>
            </div>
        </div>
    );
}
