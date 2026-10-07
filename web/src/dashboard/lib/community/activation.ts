import { onboardingDashboardPath, onboardingEntry, type ActivationIntent, type OnboardingMode } from './onboarding';

let initialization: Promise<{ mode: OnboardingMode | null; intent: ActivationIntent | null }> | undefined;
let pending: Promise<unknown> = Promise.resolve();

// Serialize cookie changes so cancelling an in-flight lookup cannot restore its intent.
function intentRequest(method: 'GET' | 'POST' | 'DELETE', body?: { deviceId: string; claimToken?: string }): Promise<ActivationIntent | null> {
    const request = pending.catch(() => {}).then(async () => {
        const response = await fetch('/api/activation/intent', {
            method, credentials: 'same-origin', cache: 'no-store',
            headers: method !== 'GET' ? { 'Content-Type': 'application/json' } : undefined,
            body: body ? JSON.stringify(body) : undefined,
            signal: AbortSignal.timeout(15_000),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result?.error === 'string' ? result.error : 'Unable to open this payload. Please try again.');
        return result.intent ?? null;
    });
    pending = request;
    return request;
}

export function initializeOnboarding() {
    if (initialization) return initialization;
    const entry = onboardingEntry(location.href);
    // The QR credential never enters storage, the callback URL, or a rendered field.
    if (entry?.direct) history.replaceState(history.state, '', onboardingDashboardPath(entry.mode));
    initialization = (async () => {
        if (!entry) return { mode: null, intent: null };
        if (entry.mode === 'reserve') return { mode: entry.mode, intent: null };
        const intent = entry.direct
            ? entry.deviceId ? await intentRequest('POST', { deviceId: entry.deviceId, ...(entry.claimToken ? { claimToken: entry.claimToken } : {}) }) : await intentRequest('DELETE')
            : await intentRequest('GET');
        return { mode: entry.mode, intent };
    })();
    return initialization;
}

export function beginActivation(deviceId: string) { return intentRequest('POST', { deviceId }); }
export function clearActivation() {
    initialization = undefined;
    return intentRequest('DELETE');
}
