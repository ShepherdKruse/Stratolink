import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useGlobePortal } from './globe-portal';

export type DashboardTheme = 'light' | 'dark';

const STORAGE_KEY = 'stratolink-dashboard-v2-theme';
const SYSTEM_DARK = '(prefers-color-scheme: dark)';

/** Initial theme: an explicit saved choice wins; otherwise follow the OS
 *  setting (so dark-mode users land in dark mode by default). */
function readInitialTheme(): DashboardTheme {
    if (typeof window === 'undefined') return 'light';
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'dark' || stored === 'light') return stored;
    } catch { /* Use the system setting when storage is unavailable. */ }
    return window.matchMedia?.(SYSTEM_DARK).matches ? 'dark' : 'light';
}

type DashboardThemeContextValue = {
    theme: DashboardTheme;
    setTheme: (theme: DashboardTheme) => void;
    toggleTheme: () => void;
};

const DashboardThemeContext = createContext<DashboardThemeContextValue | null>(null);

export function DashboardThemeProvider({ children }: { children: ReactNode }) {
    const stage = useGlobePortal();
    const [preference, setThemeState] = useState<DashboardTheme>(readInitialTheme);
    const [entryThemeReady, setEntryThemeReady] = useState(false);
    // The footer is part of the light homepage. Restore the dashboard palette
    // halfway through its opening rotation, without changing the saved choice.
    const theme = stage === 'footer' || (stage === 'entering' && !entryThemeReady) ? 'light' : preference;

    useEffect(() => {
        if (stage !== 'entering') {
            setEntryThemeReady(false);
            return;
        }
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const timer = window.setTimeout(() => setEntryThemeReady(true), reduced ? 0 : 800);
        return () => window.clearTimeout(timer);
    }, [stage]);

    useEffect(() => {
        /* Follow live OS changes — but only until the user picks a theme
         * themselves (a stored value means they've chosen, so stop following). */
        const mq = window.matchMedia?.(SYSTEM_DARK);
        const onChange = () => setThemeState(readInitialTheme());
        const onStorage = (event: StorageEvent) => {
            if (event.key === STORAGE_KEY || event.key === null) onChange();
        };
        mq?.addEventListener('change', onChange);
        window.addEventListener('storage', onStorage);
        return () => {
            mq?.removeEventListener('change', onChange);
            window.removeEventListener('storage', onStorage);
        };
    }, []);

    const setTheme = useCallback((next: DashboardTheme) => {
        setThemeState(next);
        try { localStorage.setItem(STORAGE_KEY, next); } catch { /* Keep the session usable. */ }
    }, []);

    const toggleTheme = useCallback(() => {
        setThemeState((prev) => {
            const next: DashboardTheme = prev === 'light' ? 'dark' : 'light';
            try { localStorage.setItem(STORAGE_KEY, next); } catch { /* Keep the session usable. */ }
            return next;
        });
    }, []);

    return (
        <DashboardThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
            {children}
        </DashboardThemeContext.Provider>
    );
}

export function useDashboardTheme(): DashboardThemeContextValue {
    const ctx = useContext(DashboardThemeContext);
    if (!ctx) {
        throw new Error('useDashboardTheme must be used within DashboardThemeProvider');
    }
    return ctx;
}
