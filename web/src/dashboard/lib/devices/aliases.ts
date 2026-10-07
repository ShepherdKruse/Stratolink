/**
 * Maps TTN / firmware device IDs to the canonical dashboard device_id.
 * Telemetry may arrive under an alias; the dashboard always shows the canonical id.
 */
export const DEVICE_ID_ALIASES: Record<string, string> = {
    'stratolink-3-eu': 'stratolink-3',
};

export function canonicalDeviceId(deviceId: string): string {
    return DEVICE_ID_ALIASES[deviceId] ?? deviceId;
}

/** Alias rows should not appear as separate fleet entries. */
export function isHiddenAliasDevice(deviceId: string): boolean {
    return deviceId in DEVICE_ID_ALIASES;
}

/** All telemetry device_id values to query for a canonical (or alias) device. */
export function telemetryDeviceIds(deviceId: string): string[] {
    const canonical = canonicalDeviceId(deviceId);
    const aliases = Object.entries(DEVICE_ID_ALIASES)
        .filter(([, canon]) => canon === canonical)
        .map(([alias]) => alias);
    return [canonical, ...aliases];
}

/** Expand registered device ids for fleet-wide telemetry .in() queries. */
export function expandFleetDeviceIdsForTelemetry(registeredIds: string[]): string[] {
    const out = new Set<string>();
    for (const id of registeredIds) {
        for (const q of telemetryDeviceIds(id)) {
            out.add(q);
        }
    }
    return [...out];
}
