import type { TelemetryRow } from '../../components/dashboard-v2/atoms';

export function rowAtTime(rows: TelemetryRow[], time: number | null): TelemetryRow | null {
    if (!rows.length) return null;
    if (time === null) return rows[rows.length - 1];
    let selected: TelemetryRow | null = null;
    for (const row of rows) {
        if (row.t > time) break;
        selected = row;
    }
    return selected;
}

export function positionAtTime(rows: TelemetryRow[], time: number | null) {
    const fixes = rows.filter((row): row is TelemetryRow & { lat: number; lon: number } => row.lat !== null && row.lon !== null);
    if (!fixes.length || (time !== null && time < fixes[0].t)) return null;
    const last = fixes[fixes.length - 1];
    if (time === null || time >= last.t) return { lat: last.lat, lon: last.lon, altitude_m: last.alt };
    for (let index = 1; index < fixes.length; index++) {
        const next = fixes[index];
        if (time > next.t) continue;
        const previous = fixes[index - 1];
        const fraction = (time - previous.t) / (next.t - previous.t || 1);
        const longitudeDelta = ((next.lon - previous.lon + 540) % 360) - 180;
        return {
            lat: previous.lat + (next.lat - previous.lat) * fraction,
            lon: ((previous.lon + longitudeDelta * fraction + 540) % 360) - 180,
            altitude_m: time === next.t ? next.alt : previous.alt,
        };
    }
    return null;
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
        if (['landed', 'recovered', 'retired', 'lost', 'idle'].includes(device.status.toLowerCase())) return false;
        const latest = rowsByDevice[device.id]?.at(-1)?.t;
        return latest != null && latest <= now && now - latest < 15 * 60_000;
    }).length;
    return { active, inactive: devices.length - active };
}

/** The homepage prioritizes live flights, then falls back to recorded balloons. */
export function previewFleet<T extends { id: string; status: string }>(devices: T[], rowsByDevice: Record<string, TelemetryRow[]>, now: number): T[] {
    const active = devices.filter(device => fleetActivity([device], rowsByDevice, now).active > 0);
    return active.length ? active : devices.filter(device => (rowsByDevice[device.id]?.length ?? 0) > 0);
}
