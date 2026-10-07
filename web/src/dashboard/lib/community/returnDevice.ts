const devicePattern = /^[a-zA-Z0-9_-]{1,80}$/;
const returnLifetime = 15 * 60_000;

export function dashboardReturnDevice(href: string): string | null {
    const url = new URL(href);
    if (!/^\/dashboard\/?$/.test(url.pathname)) return null;
    const device = url.searchParams.get('device');
    return device && devicePattern.test(device) ? device : null;
}

export function storedReturnDevice(value: string | null, now = Date.now()): string | null {
    if (!value) return null;
    try {
        const record = JSON.parse(value);
        if (typeof record.device !== 'string' || !devicePattern.test(record.device)) return null;
        if (!Number.isFinite(record.createdAt) || record.createdAt > now || now - record.createdAt > returnLifetime) return null;
        return record.device;
    } catch { return null; }
}
