'use client';

import { format } from 'date-fns';

interface MissionTimelineProps {
    startTime: Date;
    endTime: Date;
    currentTime: Date;
    onChange: (timestamp: Date) => void;
}

export default function MissionTimeline({ startTime, endTime, currentTime, onChange }: MissionTimelineProps) {
    if (!startTime || !endTime || !currentTime) {
        return null;
    }
    
    const startTimestamp = startTime.getTime();
    const endTimestamp = endTime.getTime();
    const currentTimestamp = currentTime.getTime();
    const range = endTimestamp - startTimestamp;
    const progress = Math.max(0, Math.min(100, range > 0 ? ((currentTimestamp - startTimestamp) / range) * 100 : 0));

    // Duration in human readable format
    const durationMs = range;
    const durationHrs = Math.floor(durationMs / (1000 * 60 * 60));
    const durationMins = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = parseFloat(e.target.value);
        const newTimestamp = startTimestamp + (value / 100) * range;
        onChange(new Date(newTimestamp));
    };

    return (
        <div className="fixed bottom-3 left-1/2 transform -translate-x-1/2 z-30 w-[70%] max-w-3xl">
            <div className="bg-[#1a1a1a]/95 border border-[#333] p-3">
                {/* Top row: metadata */}
                <div className="flex items-baseline justify-between mb-2 text-[10px] font-mono">
                    <span className="text-[#666]">
                        {format(startTime, 'yyyy-MM-dd HH:mm')}
                    </span>
                    <span className="text-[#e5e5e5] font-semibold">
                        {format(currentTime, 'HH:mm:ss')} UTC
                    </span>
                    <span className="text-[#666]">
                        {format(endTime, 'yyyy-MM-dd HH:mm')}
                    </span>
                </div>

                {/* Scrubber */}
                <div className="relative h-4 flex items-center">
                    {/* Track background */}
                    <div className="absolute inset-x-0 h-[2px] bg-[#333]">
                        {/* Progress fill */}
                        <div 
                            className="h-full bg-[#4a90d9]" 
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                    {/* Input range - invisible but interactive */}
                    <input
                        type="range"
                        min="0"
                        max="100"
                        step="0.1"
                        value={progress}
                        onChange={handleChange}
                        className="absolute inset-0 w-full opacity-0 cursor-pointer"
                    />
                    {/* Thumb indicator */}
                    <div 
                        className="absolute w-2 h-2 bg-[#4a90d9] border border-[#1a1a1a] pointer-events-none"
                        style={{ left: `calc(${progress}% - 4px)` }}
                    />
                </div>

                {/* Bottom row: stats */}
                <div className="flex items-baseline justify-between mt-2 text-[9px] font-mono text-[#666]">
                    <span>Duration: {durationHrs}h {durationMins}m</span>
                    <span>Position: {progress.toFixed(1)}%</span>
                    <span>Points: {Math.floor(progress)}+</span>
                </div>
            </div>
        </div>
    );
}
