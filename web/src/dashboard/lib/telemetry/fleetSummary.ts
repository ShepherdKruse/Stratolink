import type { DeviceSummary } from '../../components/dashboard-v2/useTelemetry';
import type { TelemetryRow } from '../../components/dashboard-v2/atoms';

export function shouldPollTelemetry(status: string): boolean {
    return !['landed', 'recovered', 'retired', 'planned'].includes(status.toLowerCase());
}

/** Reuse the same sanitized history for cards, activity filters, and map positions. */
export function withLatestTelemetry(device: DeviceSummary, rows: TelemetryRow[] | undefined): DeviceSummary {
    if (!rows?.length) return device;
    let fix: TelemetryRow | undefined;
    for (let i = rows.length - 1; i >= 0; i--) {
        if (rows[i].lat !== null && rows[i].lon !== null) { fix = rows[i]; break; }
    }
    return {
        ...device,
        lastContactT: rows[rows.length - 1].t,
        latestFix: fix ? { lat: fix.lat!, lon: fix.lon!, alt: fix.alt, t: fix.t } : device.latestFix,
    };
}
