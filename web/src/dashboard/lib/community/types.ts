import type { DeviceSummary } from '../../components/dashboard-v2/useTelemetry';

export type AccountUser = { id: string; login: string; avatarUrl: string | null };
export type TTNCluster = 'nam1' | 'eu1' | 'au1';
export type TTNConnection = {
    id: string;
    cluster: TTNCluster;
    applicationId: string;
    devEui: string;
    region: string;
    connectedAt: string;
    lastReceivedAt?: string | null;
};
export type RegisteredBalloon = {
    id: string;
    callsign: string;
    status: string;
    devEui: string;
    ownerId: string;
    ownerGithub: string;
    registeredAt: string;
    launchedAt: number | null;
    connections: TTNConnection[];
    connectionStatus: 'pending' | 'connected';
};
export type AccountResponse = { user: AccountUser; balloons: RegisteredBalloon[] };
export type ConnectionInput = { cluster: TTNCluster; applicationId: string; deviceEui: string; apiKey: string };
export type ConnectionResponse = { balloon: RegisteredBalloon; webhook?: { url: string; secret: string } };

export function mergeRegisteredBalloons(devices: DeviceSummary[], owned: RegisteredBalloon[]): DeviceSummary[] {
    const merged = new Map(devices.map(device => [device.id, device]));
    for (const balloon of owned) {
        const existing = merged.get(balloon.id);
        merged.set(balloon.id, {
            ...existing,
            id: balloon.id,
            callsign: balloon.callsign,
            status: balloon.status,
            ownerId: balloon.ownerId,
            ownerGithub: balloon.ownerGithub,
            connectionStatus: balloon.connectionStatus,
            launchedAt: balloon.launchedAt,
            launchLat: existing?.launchLat ?? null,
            launchLon: existing?.launchLon ?? null,
            lastContactT: existing?.lastContactT ?? null,
            latestFix: existing?.latestFix ?? null,
        });
    }
    return [...merged.values()];
}
