'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';

interface TelemetryData {
    id: string;
    device_id: string;
    received_at: string;
    latitude?: number;
    longitude?: number;
    altitude?: number;
    battery_voltage?: number;
}

export default function Dashboard() {
    const [telemetry, setTelemetry] = useState<TelemetryData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchTelemetry() {
            const supabase = createClient();
            
            const { data, error } = await supabase
                .from('telemetry')
                .select('*')
                .order('received_at', { ascending: false })
                .limit(100);
            
            if (error) {
                console.error('Error fetching telemetry:', error);
            } else {
                setTelemetry(data || []);
            }
            
            setLoading(false);
        }
        
        fetchTelemetry();
    }, []);

    if (loading) {
        return <div>Loading telemetry data...</div>;
    }

    return (
        <div>
            <h1>Stratolink Dashboard</h1>
            <div>
                <h2>Recent Telemetry</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Device ID</th>
                            <th>Received At</th>
                            <th>Latitude</th>
                            <th>Longitude</th>
                            <th>Altitude</th>
                            <th>Battery</th>
                        </tr>
                    </thead>
                    <tbody>
                        {telemetry.map((entry) => (
                            <tr key={entry.id}>
                                <td>{entry.device_id}</td>
                                <td>{new Date(entry.received_at).toLocaleString()}</td>
                                <td>{entry.latitude?.toFixed(6)}</td>
                                <td>{entry.longitude?.toFixed(6)}</td>
                                <td>{entry.altitude?.toFixed(0)} m</td>
                                <td>{entry.battery_voltage?.toFixed(2)} V</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {/* TODO: Integrate map component for visualization */}
        </div>
    );
}
