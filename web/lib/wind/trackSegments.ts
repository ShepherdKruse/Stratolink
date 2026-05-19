import type { V2FlightPoint } from '@/components/dashboard-v2/V2MissionMap';

const EPS = 0.0008;
const FREEZE_MIN_MS = 18 * 60_000;

export type TrackSegments = {
    observed: V2FlightPoint[];
    freezeDrift: Array<[number, number]>;
    resumed: V2FlightPoint[];
};

/** Split track into observed, implied GPS-freeze drift, and post-resume segments when detectable. */
export function splitTrackSegments(track: V2FlightPoint[]): TrackSegments {
    if (track.length < 3) {
        return { observed: track, freezeDrift: [], resumed: [] };
    }

    let freezeStart = -1;
    let freezeEnd = -1;

    for (let i = 1; i < track.length; i++) {
        const prev = track[i - 1];
        const cur = track[i];
        const same =
            Math.abs(cur.lat - prev.lat) < EPS &&
            Math.abs(cur.lon - prev.lon) < EPS &&
            new Date(cur.t).getTime() - new Date(prev.t).getTime() >= FREEZE_MIN_MS;

        if (same && freezeStart < 0) freezeStart = i - 1;
        if (freezeStart >= 0 && !same) {
            freezeEnd = i - 1;
            break;
        }
    }

    if (freezeStart < 0 || freezeEnd < 0 || freezeEnd <= freezeStart) {
        return { observed: track, freezeDrift: [], resumed: [] };
    }

    const observed = track.slice(0, freezeStart + 1);
    const resumedPts = track.slice(freezeEnd);
    const a = observed[observed.length - 1];
    const b = resumedPts[0];
    const freezeDrift: Array<[number, number]> =
        a && b ? [[a.lon, a.lat], [b.lon, b.lat]] : [];

    return { observed, freezeDrift, resumed: resumedPts };
}
