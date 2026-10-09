import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { accountRequest, AccountRequestError, authClient, clearOAuthReturnState, finishOAuthRedirect, isAuthConfigured, signInWithGithub } from '@/lib/community/auth';
import type { AccountResponse, AccountUser, BalloonSettings, ConnectionInput, ConnectionResponse, RegisteredBalloon } from '@/lib/community/types';
import { beginActivation, clearActivation, initializeOnboarding } from '@/lib/community/activation';
import { onboardingDashboardPath, onboardingEntry, type ActivationIntent, type OnboardingMode } from '@/lib/community/onboarding';
import { dashboardReturnDevice } from '@/lib/community/returnDevice';

type Community = {
    user: AccountUser | null;
    account: string | null;
    balloons: RegisteredBalloon[];
    loading: boolean;
    busy: boolean;
    error: string;
    revision: number;
    panel: 'register' | 'manage' | OnboardingMode | null;
    setPanel: (panel: Community['panel']) => void;
    signIn: () => Promise<void>;
    signOut: () => Promise<void>;
    register: (input: BalloonSettings) => Promise<void>;
    update: (id: string, input: string | BalloonSettings) => Promise<void>;
    connect: (id: string, input: ConnectionInput) => Promise<ConnectionResponse>;
    intent: ActivationIntent | null;
    activationLoading: boolean;
    activationError: string;
    focusDevice: string | null;
    openPayload: (deviceId: string) => Promise<void>;
    claimPayload: (claimToken?: string) => Promise<void>;
    managePayload: (deviceId: string) => void;
    reserve: (callsign: string) => Promise<void>;
};
const Context = createContext<Community | null>(null);

export function CommunityProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AccountUser | null>(null);
    const [balloons, setBalloons] = useState<RegisteredBalloon[]>([]);
    const [panel, setPanel] = useState<Community['panel']>(() => onboardingEntry(location.href)?.mode ?? null);
    const [onboarding, setOnboarding] = useState<OnboardingMode | null>(() => onboardingEntry(location.href)?.mode ?? null);
    const [intent, setIntent] = useState<ActivationIntent | null>(null);
    const [activationLoading, setActivationLoading] = useState(() => onboardingEntry(location.href)?.mode === 'activate');
    const [activationError, setActivationError] = useState('');
    const [focusDevice, setFocusDevice] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [revision, setRevision] = useState(0);
    const generation = useRef(0);
    const refreshSequence = useRef(0);
    const principal = useRef<string | null>(null);
    const mutating = useRef(false);
    const intentSequence = useRef(0);

    const dismissOnboarding = useCallback(() => {
        intentSequence.current++;
        setOnboarding(null); setIntent(null); setActivationLoading(false); setActivationError(''); setFocusDevice(null);
        clearOAuthReturnState();
        if (onboardingEntry(location.href)) history.replaceState(history.state, '', onboardingDashboardPath(null, dashboardReturnDevice(location.href)));
        void clearActivation().catch(() => {});
    }, []);

    useEffect(() => {
        const sequence = ++intentSequence.current;
        void initializeOnboarding().then(result => {
            if (sequence !== intentSequence.current) return;
            setOnboarding(result.mode); setIntent(result.intent);
            if (result.mode) setPanel(result.mode);
        }).catch(error => {
            if (sequence === intentSequence.current) setActivationError(error instanceof Error ? error.message : 'Unable to open this payload.');
        }).finally(() => { if (sequence === intentSequence.current) setActivationLoading(false); });
        return () => { intentSequence.current++; };
    }, []);

    const clearAccount = useCallback(() => {
        generation.current++;
        setUser(null);
        setBalloons([]);
        setPanel(current => current === 'activate' || current === 'reserve' ? current : null);
    }, []);
    const refresh = useCallback(async () => {
        const request = ++refreshSequence.current;
        const session = generation.current;
        try {
            const account = await accountRequest<AccountResponse>('/api/account');
            if (request !== refreshSequence.current || session !== generation.current) return;
            setUser(account.user);
            setBalloons(account.balloons);
            setError('');
        } catch (error) {
            if (request !== refreshSequence.current || session !== generation.current) return;
            if (error instanceof AccountRequestError && error.status === 401) clearAccount();
            else setError(error instanceof Error ? error.message : 'Unable to load your account.');
        } finally { if (request === refreshSequence.current) setLoading(false); }
    }, [clearAccount]);

    useEffect(() => {
        let cancelled = false;
        let unsubscribe: (() => void) | undefined;
        let refreshTimer: ReturnType<typeof setTimeout> | undefined;
        async function initialize() {
            if (!isAuthConfigured()) { setLoading(false); return; }
            try {
                await finishOAuthRedirect();
                if (cancelled) return;
                const { data: { subscription } } = authClient().auth.onAuthStateChange((event, session) => {
                    if (event === 'SIGNED_OUT') { principal.current = null; clearAccount(); dismissOnboarding(); setPanel(null); setLoading(false); return; }
                    const nextPrincipal = session?.user.id ?? null;
                    if (nextPrincipal !== principal.current) { principal.current = nextPrincipal; clearAccount(); }
                    // Auth callbacks hold a client lock. Fetch the account after it is released.
                    clearTimeout(refreshTimer);
                    refreshTimer = setTimeout(() => { if (!cancelled) void refresh(); }, 0);
                });
                unsubscribe = () => subscription.unsubscribe();
                await refresh();
            } catch (error) {
                if (!cancelled) { setError(error instanceof Error ? error.message : 'Sign-in is unavailable.'); setLoading(false); }
            }
        }
        void initialize();
        return () => { cancelled = true; generation.current++; clearTimeout(refreshTimer); unsubscribe?.(); };
    }, [refresh, clearAccount, dismissOnboarding]);

    async function mutate<T>(action: () => Promise<T>, save: (result: T) => void): Promise<T> {
        if (mutating.current) throw new Error('Wait for the current request to finish.');
        const request = generation.current;
        mutating.current = true;
        setBusy(true);
        setError('');
        try {
            const result = await action();
            if (request !== generation.current) throw new Error('Your session changed. Please try again.');
            save(result);
            return result;
        } catch (error) {
            if (error instanceof AccountRequestError && error.status === 401) clearAccount();
            throw error;
        } finally { mutating.current = false; setBusy(false); }
    }
    function saveBalloon(balloon: RegisteredBalloon) {
        refreshSequence.current++;
        setBalloons(current => [...current.filter(existing => existing.id !== balloon.id), balloon]);
        setRevision(current => current + 1);
    }
    const value: Community = {
        user, account: user?.login ?? null, balloons, loading, busy, error, revision, panel,
        intent, activationLoading, activationError, focusDevice,
        setPanel(next) {
            if (mutating.current) return;
            if (user || next === null) {
                if (onboarding) dismissOnboarding();
                setPanel(next);
            }
        },
        async signIn() {
            setBusy(true); setError('');
            try { await signInWithGithub(onboarding); }
            catch (error) { setError(error instanceof Error ? error.message : 'Unable to sign in.'); }
            finally { setBusy(false); }
        },
        async signOut() {
            setBusy(true); setError('');
            try {
                const { error } = await authClient().auth.signOut({ scope: 'local' });
                if (error) throw error;
                clearAccount();
                dismissOnboarding(); setPanel(null);
            } catch { setError('Unable to sign out. Please try again.'); }
            finally { setBusy(false); }
        },
        async register(input) {
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>('/api/balloons', 'POST', input), ({ balloon }) => {
                saveBalloon(balloon);
                setPanel('manage');
            });
        },
        async update(id, input) {
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>(`/api/balloons/${encodeURIComponent(id)}`, 'PATCH', typeof input === 'string' ? { status: input } : input), ({ balloon }) => saveBalloon(balloon));
        },
        async connect(id, input) {
            return mutate(() => accountRequest<ConnectionResponse>(`/api/balloons/${encodeURIComponent(id)}/connections`, 'POST', input), result => saveBalloon(result.balloon));
        },
        async openPayload(deviceId) {
            const sequence = ++intentSequence.current;
            setActivationLoading(true); setActivationError('');
            try {
                const next = deviceId.trim() ? await beginActivation(deviceId.trim()) : await clearActivation();
                if (sequence === intentSequence.current) setIntent(next);
            } catch (error) {
                if (sequence === intentSequence.current) setActivationError(error instanceof Error ? error.message : 'Unable to open this payload.');
            } finally { if (sequence === intentSequence.current) setActivationLoading(false); }
        },
        async claimPayload(claimToken) {
            if (!intent) throw new Error('Open your payload link again.');
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>('/api/activation/claim', 'POST', { deviceId: intent.deviceId, ...(claimToken ? { claimToken } : {}) }, 'same-origin'), ({ balloon }) => {
                saveBalloon(balloon); dismissOnboarding(); setPanel('manage'); setFocusDevice(balloon.id);
                history.replaceState(history.state, '', onboardingDashboardPath(null, balloon.id));
            });
        },
        managePayload(deviceId) {
            if (mutating.current || !user || !balloons.some(balloon => balloon.id === deviceId)) return;
            dismissOnboarding(); setPanel('manage'); setFocusDevice(deviceId);
            history.replaceState(history.state, '', onboardingDashboardPath(null, deviceId));
        },
        async reserve(callsign) {
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>('/api/balloons/reserve', 'POST', { callsign: callsign.trim() }), ({ balloon }) => {
                saveBalloon(balloon); dismissOnboarding(); setPanel('manage');
            });
        },
    };
    return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useCommunity() {
    const value = useContext(Context);
    if (!value) throw new Error('Community provider is missing');
    return value;
}
