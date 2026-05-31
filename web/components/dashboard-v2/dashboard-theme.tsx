'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

export type DashboardTheme = 'light' | 'dark';

const STORAGE_KEY = 'stratolink-dashboard-v2-theme';

function readStoredTheme(): DashboardTheme {
    if (typeof window === 'undefined') return 'light';
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
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
        setThemeState(readStoredTheme());
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
