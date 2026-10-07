import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { registrationValues } from '@/lib/telemetry/fleetFilters';
import { accountRequest, AccountRequestError, authClient, finishOAuthRedirect, isAuthConfigured, signInWithGithub } from '@/lib/community/auth';
import type { AccountResponse, AccountUser, ConnectionInput, ConnectionResponse, RegisteredBalloon } from '@/lib/community/types';

type Community = {
    user: AccountUser | null;
    account: string | null;
    balloons: RegisteredBalloon[];
    loading: boolean;
    busy: boolean;
    error: string;
    revision: number;
    panel: 'register' | 'manage' | null;
    setPanel: (panel: Community['panel']) => void;
    signIn: () => Promise<void>;
    signOut: () => Promise<void>;
    register: (callsign: string, devEui: string) => Promise<void>;
    update: (id: string, status: string) => Promise<void>;
    connect: (id: string, input: ConnectionInput) => Promise<ConnectionResponse>;
};
const Context = createContext<Community | null>(null);

export function CommunityProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AccountUser | null>(null);
    const [balloons, setBalloons] = useState<RegisteredBalloon[]>([]);
    const [panel, setPanel] = useState<Community['panel']>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [revision, setRevision] = useState(0);
    const generation = useRef(0);
    const refreshSequence = useRef(0);
    const principal = useRef<string | null>(null);
    const mutating = useRef(false);

    const clearAccount = useCallback(() => {
        generation.current++;
        setUser(null);
        setBalloons([]);
        setPanel(null);
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
                    if (event === 'SIGNED_OUT') { clearAccount(); setLoading(false); return; }
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
    }, [refresh, clearAccount]);

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
        setPanel(next) { if (user || next === null) setPanel(next); },
        async signIn() {
            setBusy(true); setError('');
            try { await signInWithGithub(); }
            catch (error) { setError(error instanceof Error ? error.message : 'Unable to sign in.'); }
            finally { setBusy(false); }
        },
        async signOut() {
            setBusy(true); setError('');
            try {
                const { error } = await authClient().auth.signOut({ scope: 'local' });
                if (error) throw error;
                clearAccount();
            } catch { setError('Unable to sign out. Please try again.'); }
            finally { setBusy(false); }
        },
        async register(callsign, devEui) {
            const input = registrationValues(callsign, devEui);
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>('/api/balloons', 'POST', input), ({ balloon }) => {
                saveBalloon(balloon);
                setPanel('manage');
            });
        },
        async update(id, status) {
            await mutate(() => accountRequest<{ balloon: RegisteredBalloon }>(`/api/balloons/${encodeURIComponent(id)}`, 'PATCH', { status }), ({ balloon }) => saveBalloon(balloon));
        },
        async connect(id, input) {
            return mutate(() => accountRequest<ConnectionResponse>(`/api/balloons/${encodeURIComponent(id)}/connections`, 'POST', input), result => saveBalloon(result.balloon));
        },
    };
    return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useCommunity() {
    const value = useContext(Context);
    if (!value) throw new Error('Community provider is missing');
    return value;
}
