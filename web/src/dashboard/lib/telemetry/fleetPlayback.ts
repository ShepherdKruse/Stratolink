import type { TelemetryRow } from '../../components/dashboard-v2/atoms';

export function rowAtTime(rows: TelemetryRow[], time: number | null): TelemetryRow | null {
    if (!rows.length) return null;
    if (time === null) return rows[rows.length - 1];
    let low = 0, high = rows.length;
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (rows[middle].t <= time) low = middle + 1;
        else high = middle;
    }
    return rows[low - 1] ?? null;
}

// History arrays are replaced on refresh, so their GPS index can be reused while scrubbing.
const gpsIndices = new WeakMap<TelemetryRow[], Array<TelemetryRow & { lat: number; lon: number }>>();
const altitudeIndices = new WeakMap<TelemetryRow[], TelemetryRow[]>();

export function altitudeAtTime(rows: TelemetryRow[], time: number) {
    let measured = altitudeIndices.get(rows);
    if (!measured) {
        measured = rows.filter(row => row.presAlt != null || row.alt != null);
        altitudeIndices.set(rows, measured);
    }
    const row = rowAtTime(measured, time);
    return row?.presAlt ?? row?.alt ?? null;
}

export function positionAtTime(rows: TelemetryRow[], time: number | null) {
    let fixes = gpsIndices.get(rows);
    if (!fixes) {
        fixes = rows.filter((row): row is TelemetryRow & { lat: number; lon: number } => row.lat !== null && row.lon !== null);
        gpsIndices.set(rows, fixes);
    }
    if (!fixes.length || (time !== null && time < fixes[0].t)) return null;
    const last = fixes[fixes.length - 1];
    if (time === null || time >= last.t) return { lat: last.lat, lon: last.lon, altitude_m: last.alt };
    let low = 1, high = fixes.length - 1;
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (fixes[middle].t < time) low = middle + 1;
        else high = middle;
    }
    const next = fixes[low], previous = fixes[low - 1];
    const fraction = (time - previous.t) / (next.t - previous.t || 1);
    const longitudeDelta = ((next.lon - previous.lon + 540) % 360) - 180;
    return {
        lat: previous.lat + (next.lat - previous.lat) * fraction,
        lon: ((previous.lon + longitudeDelta * fraction + 540) % 360) - 180,
        altitude_m: time === next.t ? next.alt : previous.alt,
    };
}

export function balloonName(device: { callsign: string | null; id: string }) {
    return (device.callsign || device.id).replace(/^stratolink[- ](\d+)$/i, 'Stratolink $1');
}

/** Active means a recent uplink from a mission that is not marked complete. */
export function fleetActivity(
    devices: Array<{ id: string; status: string }>,
    rowsByDevice: Record<string, TelemetryRow[]>,
    now: number,
) {
    const active = devices.filter(device => {
        if (['landed', 'recovered', 'retired', 'lost', 'idle', 'planned', 'storage'].includes(device.status.toLowerCase())) return false;
        const latest = rowsByDevice[device.id]?.at(-1)?.t;
        return latest != null && latest <= now && now - latest < 15 * 60_000;
    }).length;
    return { active, inactive: devices.length - active };
}

/** The homepage prioritizes live flights, then falls back to recorded balloons. */
export function previewFleet<T extends { id: string; status: string }>(devices: T[], rowsByDevice: Record<string, TelemetryRow[]>, now: number): T[] {
    const flown = devices.filter(device => !['planned', 'storage', 'idle'].includes(device.status.toLowerCase()));
    const active = flown.filter(device => fleetActivity([device], rowsByDevice, now).active > 0);
    return active.length ? active : flown.filter(device => (rowsByDevice[device.id]?.length ?? 0) > 0);
}
