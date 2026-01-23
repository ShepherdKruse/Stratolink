'use client';

import { useState, useEffect } from 'react';
import MissionMap from '@/components/MissionMap';
import { createClient } from '@/lib/supabase';

export default function MissionControl() {
    const [projection, setProjection] = useState<'globe' | 'mercator'>('globe');
    const [activeCount, setActiveCount] = useState(0);
    const [landedCount, setLandedCount] = useState(0);

    // Fetch balloon counts from Supabase
    useEffect(() => {
        async function fetchFleetStatus() {
            // Check if Supabase is configured
            const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
            if (!supabaseUrl || supabaseUrl.includes('your_supabase') || supabaseUrl === '') {
                // Supabase not configured yet, skip fetching
                return;
            }

            try {
                const supabase = createClient();
                
                // Get active balloons (recent telemetry within last hour)
                const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                
                const { data: active, error: activeError } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact', head: true })
                    .gte('time', oneHourAgo);
                
                if (!activeError && active) {
                    setActiveCount(active.length || 0);
                }

                // Get landed balloons (altitude < 100m in last 24 hours)
                const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                
                const { data: landed, error: landedError } = await supabase
                    .from('telemetry')
                    .select('device_id', { count: 'exact', head: true })
                    .gte('time', oneDayAgo)
                    .lt('altitude_m', 100);
                
                if (!landedError && landed) {
                    setLandedCount(landed.length || 0);
                }
            } catch (error) {
                // Silently handle Supabase errors if not configured
                console.debug('Supabase not configured or error:', error);
            }
        }

        fetchFleetStatus();
        // Refresh every 30 seconds
        const interval = setInterval(fetchFleetStatus, 30000);
        
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="w-screen h-screen relative overflow-hidden">
            {/* Full-screen 3D Map */}
            <div className="absolute inset-0">
                <MissionMap 
                    projection={projection}
                    onProjectionChange={setProjection}
                />
            </div>

            {/* Glassmorphism Sidebar */}
            <div className="absolute left-0 top-0 h-full w-80 backdrop-blur-md bg-black/30 border-r border-white/10 z-10 p-6 flex flex-col">
                <div className="mb-8">
                    <h1 className="text-2xl font-bold text-white mb-2">Mission Control</h1>
                    <p className="text-gray-400 text-sm">Stratolink Fleet Dashboard</p>
                </div>

                {/* Fleet Status */}
                <div className="mb-8 space-y-4">
                    <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-gray-400 text-sm">Active Balloons</span>
                            <span className="text-cyan-400 text-2xl font-bold">{activeCount}</span>
                        </div>
                    </div>
                    <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-gray-400 text-sm">Landed</span>
                            <span className="text-gray-400 text-2xl font-bold">{landedCount}</span>
                        </div>
                    </div>
                </div>

                {/* Projection Toggle */}
                <div className="mt-auto">
                    <button
                        onClick={() => setProjection(projection === 'globe' ? 'mercator' : 'globe')}
                        className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/50 text-cyan-400 px-4 py-3 rounded-lg font-medium transition-colors"
                    >
                        {projection === 'globe' ? 'Switch to 2D' : 'Switch to 3D Globe'}
                    </button>
                </div>
            </div>
        </div>
    );
}
