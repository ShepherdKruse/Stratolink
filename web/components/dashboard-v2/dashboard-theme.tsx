'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

export type DashboardTheme = 'light' | 'dark';

const STORAGE_KEY = 'stratolink-dashboard-v2-theme';
const SYSTEM_DARK = '(prefers-color-scheme: dark)';

/** Initial theme: an explicit saved choice wins; otherwise follow the OS
 *  setting (so dark-mode users land in dark mode by default). */
function readInitialTheme(): DashboardTheme {
    if (typeof window === 'undefined') return 'light';
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia?.(SYSTEM_DARK).matches ? 'dark' : 'light';
}

type DashboardThemeContextValue = {
    theme: DashboardTheme;
    setTheme: (theme: DashboardTheme) => void;
    toggleTheme: () => void;
};

const DashboardThemeContext = createContext<DashboardThemeContextValue | null>(null);

export function DashboardThemeProvider({ children }: { children: ReactNode }) {
    const [theme, setThemeState] = useState<DashboardTheme>('light');

    useEffect(() => {
        setThemeState(readInitialTheme());

        /* Follow live OS changes — but only until the user picks a theme
         * themselves (a stored value means they've chosen, so stop following). */
        const mq = window.matchMedia?.(SYSTEM_DARK);
        if (!mq) return;
        const onChange = (e: MediaQueryListEvent) => {
            if (localStorage.getItem(STORAGE_KEY)) return;
            setThemeState(e.matches ? 'dark' : 'light');
        };
        mq.addEventListener('change', onChange);
        return () => mq.removeEventListener('change', onChange);
    }, []);

    const setTheme = useCallback((next: DashboardTheme) => {
        setThemeState(next);
        localStorage.setItem(STORAGE_KEY, next);
    }, []);

    const toggleTheme = useCallback(() => {
        setThemeState((prev) => {
            const next: DashboardTheme = prev === 'light' ? 'dark' : 'light';
            localStorage.setItem(STORAGE_KEY, next);
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
