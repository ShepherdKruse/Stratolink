import { useEffect, useState } from 'react';
import { forecastRequests } from '@/lib/telemetry/forecastRequests';
import { cleanReconstructedTrack } from '@/lib/telemetry/reconstructedTrack';
import type { TimedPosition } from '@/lib/telemetry/flightTail';

/** Reuse the detail view's stored historical winds, only while fleet paths are visible. */
export function useFleetReconstruction(deviceIds: string[]) {
    const [tracks, setTracks] = useState<Record<string, TimedPosition[]>>({});
    const idsKey = JSON.stringify([...deviceIds].sort());
    useEffect(() => {
        const stops = (JSON.parse(idsKey) as string[]).map(id => forecastRequests.watch(id, result => {
            if (result.status === 202 || result.status === 0 || result.status >= 500) return;
            const track = cleanReconstructedTrack(result.data?.observed?.reconstructed_track);
            setTracks(current => ({ ...current, [id]: track }));
        }, false, 'history'));
        return () => stops.forEach(stop => stop());
    }, [idsKey]);
    return tracks;
}
