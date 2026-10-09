import type { DeviceSummary } from '../../components/dashboard-v2/useTelemetry';

export type FleetFilters = { query: string; sort: 'alphabetical' | 'newest' | 'oldest'; active: boolean; inactive: boolean; planned: boolean; mine: boolean };
export const defaultFleetFilters: FleetFilters = { query: '', sort: 'alphabetical', active: true, inactive: true, planned: false, mine: false };
export function isPlannedBalloon(status: string) {
    return ['planned', 'storage', 'idle'].includes(status.toLowerCase());
}
export function isActiveBalloon(device: Pick<DeviceSummary, 'status' | 'lastContactT'>, now: number) {
    if (['landed', 'recovered', 'retired', 'lost', 'missing', 'storage', 'idle', 'planned'].includes(device.status.toLowerCase())) return false;
    return device.lastContactT != null && device.lastContactT <= now && now - device.lastContactT < 15 * 60_000;
}
export function filterFleet<T extends DeviceSummary>(devices: T[], filters: FleetFilters, owner: string | null, now: number): T[] {
    const normalize = (value: string) => value.trim().toLowerCase().replace(/[-_]+/g, ' ');
    const query = normalize(filters.query);
    return devices.filter(device => {
        const active = isActiveBalloon(device, now);
        return (isPlannedBalloon(device.status) ? filters.planned : active ? filters.active : filters.inactive)
            && (!filters.mine || (owner !== null && (device.ownerId === owner || device.managedByUserId === owner)))
            && normalize(`${device.callsign ?? ''} ${device.id} ${device.ownerGithub ?? ''}`).includes(query);
    }).sort((a, b) => {
        if (filters.sort !== 'alphabetical') {
            if (a.launchedAt == null && b.launchedAt != null) return 1;
            if (b.launchedAt == null && a.launchedAt != null) return -1;
            const difference = (a.launchedAt ?? 0) - (b.launchedAt ?? 0);
            if (difference) return filters.sort === 'oldest' ? difference : -difference;
        }
        return (a.callsign || a.id).localeCompare(b.callsign || b.id, 'en', { numeric: true });
    });
}
export function registeredStatus(status: string): string | null {
    return ({landed:'Landed', recovered:'Landed', missing:'Missing', lost:'Missing', retired:'Retired', storage:'Planned', idle:'Planned', planned:'Planned'} as Record<string,string>)[status.toLowerCase()] ?? null;
}
