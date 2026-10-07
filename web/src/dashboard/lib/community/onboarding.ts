export type OnboardingMode = 'activate' | 'reserve';
export type ActivationIntent = { deviceId: string; requiresProof: boolean; expiresAt: string };
export type OnboardingEntry = { mode: OnboardingMode; deviceId?: string; claimToken?: string; direct: boolean };

const devicePattern = /^[a-zA-Z0-9_-]{1,80}$/;
const tokenPattern = /^[a-zA-Z0-9_-]{43}$/;

export function onboardingEntry(href: string): OnboardingEntry | null {
    const url = new URL(href);
    if (/^\/claim\/?$/.test(url.pathname)) return { mode: 'reserve', direct: true };
    const activate = url.pathname.match(/^\/activate(?:\/([^/]+))?\/?$/);
    if (activate) {
        let deviceId: string | undefined;
        try { deviceId = activate[1] ? decodeURIComponent(activate[1]) : undefined; } catch { /* Invalid IDs use manual entry. */ }
        if (deviceId && !devicePattern.test(deviceId)) deviceId = undefined;
        const fragmentTokens = new URLSearchParams(url.hash.slice(1)).getAll('k');
        const queryTokens = url.searchParams.getAll('k');
        // A single fragment credential is preferred. Ambiguous links keep context only.
        const token = fragmentTokens.length + queryTokens.length === 1 ? fragmentTokens[0] ?? queryTokens[0] : undefined;
        return { mode: 'activate', direct: true, deviceId, ...(deviceId && token && tokenPattern.test(token) ? { claimToken: token } : {}) };
    }
    if (/^\/dashboard\/?$/.test(url.pathname)) {
        const mode = url.searchParams.get('onboarding');
        if (mode === 'activate' || mode === 'reserve') return { mode, direct: false };
    }
    return null;
}

export function onboardingDashboardPath(mode: OnboardingMode | null, device?: string | null): string {
    const params = new URLSearchParams();
    if (device && devicePattern.test(device)) params.set('device', device);
    if (mode) params.set('onboarding', mode);
    return `/dashboard${params.size ? `?${params}` : ''}`;
}

export function validClaimToken(value: string): boolean { return tokenPattern.test(value); }
