import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { dashboardReturnDevice, storedReturnState } from './returnDevice';
import { onboardingDashboardPath, type OnboardingMode } from './onboarding';

let client: SupabaseClient | null = null;
let callback: Promise<void> | null = null;
const returnKey = 'stratolink-auth-return-device';

export function isAuthConfigured() {
    return Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY);
}

export function authClient() {
    if (client) return client;
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
    if (!url || !key) throw new Error('Sign-in is unavailable. Please try again later.');
    client = createClient(url, key, {
        auth: { flowType: 'pkce', persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
    });
    return client;
}

export function finishOAuthRedirect(): Promise<void> {
    if (callback) return callback;
    callback = (async () => {
        const url = new URL(location.href);
        const code = url.searchParams.get('code');
        const failed = url.searchParams.has('error') || url.hash.includes('error=');
        if (!code && !failed) return;
        // Callback state is never a destination, and OAuth data never remains in history.
        let device = dashboardReturnDevice(url.href);
        let onboarding: OnboardingMode | undefined;
        try {
            const saved = storedReturnState(sessionStorage.getItem(returnKey));
            device = saved?.device ?? device;
            onboarding = saved?.onboarding;
            sessionStorage.removeItem(returnKey);
        } catch { /* Sign-in still works when optional return-state storage is unavailable. */ }
        history.replaceState(history.state, '', onboardingDashboardPath(onboarding ?? null, device));
        if (failed) throw new Error('GitHub sign-in was not completed. Please try again.');
        if (code) {
            const { error } = await authClient().auth.exchangeCodeForSession(code);
            if (error) throw new Error('The sign-in link has expired. Please sign in again.');
        }
    })();
    return callback;
}

export function clearOAuthReturnState() {
    try { sessionStorage.removeItem(returnKey); } catch { /* Storage is optional. */ }
}

export async function signInWithGithub(onboarding?: OnboardingMode | null) {
    try {
        const device = dashboardReturnDevice((window.top ?? window).location.href);
        if (device || onboarding) sessionStorage.setItem(returnKey, JSON.stringify({ ...(device ? { device } : {}), ...(onboarding ? { onboarding } : {}), createdAt: Date.now() }));
        else sessionStorage.removeItem(returnKey);
    } catch {
        if (onboarding) throw new Error('Unable to save this payload link. Allow browser storage and try again.');
    }
    const { data, error } = await authClient().auth.signInWithOAuth({
        provider: 'github',
        options: { redirectTo: new URL('/dashboard', location.origin).href, skipBrowserRedirect: true },
    });
    if (error || !data.url) throw new Error('GitHub sign-in is unavailable. Please try again.');
    // The homepage globe becomes a dashboard in an iframe. OAuth must leave that frame.
    (window.top ?? window).location.assign(data.url);
}

export class AccountRequestError extends Error {
    constructor(message: string, readonly status: number) { super(message); }
}

export async function accountRequest<T>(path: string, method = 'GET', body?: unknown, credentials: RequestCredentials = 'omit'): Promise<T> {
    const { data: { session }, error } = await authClient().auth.getSession();
    if (error || !session) throw new AccountRequestError('Sign in to continue.', 401);
    const response = await fetch(path, {
        method,
        credentials,
        cache: 'no-store',
        headers: { Authorization: `Bearer ${session.access_token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(30_000),
    });
    const result = await response.json();
    if (!response.ok) throw new AccountRequestError(
        typeof result?.message === 'string' ? result.message : typeof result?.error === 'string' ? result.error : 'Unable to save. Please try again.',
        response.status,
    );
    return result as T;
}
