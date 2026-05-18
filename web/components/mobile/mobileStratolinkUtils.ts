export type DeviceUiStatus = 'TRACKING' | 'NO GPS' | 'LANDED';

export interface MobileFleetDeviceRow {
    id: string;
    lat: number;
    lon: number;
    altitude_m: number;
    battery_voltage?: number | null;
    /** Latest row RSSI (dBm) when available */
    rssi?: number | null;
    gps_satellites?: number | null;
    launcher_name?: string;
    awaiting_gps?: boolean;
    last_contact?: string;
    velocity_heading?: number;
    /** Supabase devices.status — used for mission-scoped telemetry windows. */
    status?: string;
    /** ISO timestamp when this flight was activated; dashboard loads telemetry from here. */
    launched_at?: string | null;
}

export function deviceUiStatus(d: Pick<MobileFleetDeviceRow, 'awaiting_gps' | 'altitude_m'>): DeviceUiStatus {
    if (d.awaiting_gps) return 'NO GPS';
    if (d.altitude_m > 100) return 'TRACKING';
    return 'LANDED';
}

export function pillClass(status: DeviceUiStatus): string {
    if (status === 'TRACKING') return 'sl-pill-teal';
    if (status === 'NO GPS') return 'sl-pill-amber';
    return 'sl-pill-dim';
}

export function fmtVolts(v: number | null | undefined): string {
    if (v == null || Number.isNaN(v)) return '—';
    return `${v.toFixed(2)} V`;
}

export function fmtAltM(m: number, awaiting?: boolean): string {
    if (awaiting && m <= 0) return '—';
    if (Number.isNaN(m)) return '—';
    return `${Math.round(m)} m`;
}

export function fmtCoords(lat: number, lon: number): string {
    const ns = lat >= 0 ? 'N' : 'S';
    const ew = lon >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(4)}° ${ns}, ${Math.abs(lon).toFixed(4)}° ${ew}`;
}

/** Relative time like "23s ago" */
export function formatAge(iso?: string | null, nowMs = Date.now()): string {
    if (!iso) return '—';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return '—';
    const s = Math.max(0, Math.floor((nowMs - t) / 1000));
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 48) return `${h}h ${m % 60}m`;
    const d = Math.floor(h / 24);
    return `${d}d`;
}

export function formatUtcClock(iso?: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toISOString().substring(11, 16) + ' UTC';
}

export interface DerivedAlert {
    id: string;
    severity: 'WARN' | 'INFO';
    device: string;
    title: string;
    message: string;
    time: string;
    ageMs: number;
    resolved: boolean;
}

const UPLINK_WARN_MS = 30 * 60 * 1000;

export function deriveFleetAlerts(rows: MobileFleetDeviceRow[], nowMs = Date.now()): DerivedAlert[] {
    const active: DerivedAlert[] = [];

    for (const d of rows) {
        if (!d.last_contact) continue;

        const last = new Date(d.last_contact).getTime();
        if (Number.isNaN(last)) continue;

        const age = nowMs - last;

        if (age > UPLINK_WARN_MS) {
            const mins = Math.floor(age / 60000);
            active.push({
                id: `${d.id}-uplink`,
                severity: 'WARN',
                device: d.id,
                title: 'No uplink',
                message: `No telemetry received for ${mins} minutes.`,
                time: formatUtcClock(d.last_contact),
                ageMs: age,
                resolved: false,
            });
        } else if (d.awaiting_gps && age < 24 * 3600 * 1000) {
            active.push({
                id: `${d.id}-nogps`,
                severity: 'WARN',
                device: d.id,
                title: 'GPS dropout',
                message: 'Packets reporting without GPS fix.',
                time: formatUtcClock(d.last_contact),
                ageMs: age,
                resolved: false,
            });
        }
    }

    return active;
}
