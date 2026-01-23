'use client';

import { format } from 'date-fns';

interface MissionTimelineProps {
    startTime: Date;
    endTime: Date;
    currentTime: Date;
    onChange: (timestamp: Date) => void;
}

export default function MissionTimeline({ startTime, endTime, currentTime, onChange }: MissionTimelineProps) {
    // Validate inputs
    if (!startTime || !endTime || !currentTime) {
        console.error('❌ MissionTimeline: Invalid time props', { startTime, endTime, currentTime });
        return null;
    }
    
    const startTimestamp = startTime.getTime();
    const endTimestamp = endTime.getTime();
    const currentTimestamp = currentTime.getTime();
    const range = endTimestamp - startTimestamp;
    const progress = Math.max(0, Math.min(100, range > 0 ? ((currentTimestamp - startTimestamp) / range) * 100 : 0));

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = parseFloat(e.target.value);
        const newTimestamp = startTimestamp + (value / 100) * range;
        const newDate = new Date(newTimestamp);
        console.log('🎚️ Timeline scrubber changed:', {
            sliderValue: value,
            newTimestamp,
            newDate: newDate.toISOString()
        });
        onChange(newDate);
    };

    return (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-30 w-[80%] max-w-4xl">
            <div className="backdrop-blur-md bg-black/60 border border-cyan-500/30 rounded-lg p-4">
                {/* Selected Time Display */}
                <div className="text-center mb-3">
                    <div className="text-cyan-400 text-xs uppercase tracking-wider mb-1">Mission Time</div>
                    <div className="text-white text-lg font-mono font-bold">
                        {format(currentTime, 'HH:mm:ss')} UTC
                    </div>
                    <div className="text-gray-400 text-xs font-mono mt-1">
                        {format(currentTime, 'yyyy-MM-dd')}
                    </div>
                </div>

                {/* Range Slider */}
                <div className="relative">
                    <input
                        type="range"
                        min="0"
                        max="100"
                        step="0.1"
                        value={progress}
                        onChange={handleChange}
                        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                        style={{
                            background: `linear-gradient(to right, rgb(6, 182, 212) 0%, rgb(6, 182, 212) ${progress}%, rgb(55, 65, 81) ${progress}%, rgb(55, 65, 81) 100%)`
                        }}
                    />
                    
                    {/* Time Labels */}
                    <div className="flex justify-between mt-2 text-xs text-gray-400 font-mono">
                        <span>{format(startTime, 'HH:mm')}</span>
                        <span>{format(endTime, 'HH:mm')}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
