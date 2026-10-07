import { useDashboardTheme } from './dashboard-theme';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faMoon, faSun } from '@fortawesome/free-solid-svg-icons';

/** Light/dark switch for dashboard v2 (default light, persisted in localStorage). */
export default function ThemeToggle() {
    const { theme, toggleTheme } = useDashboardTheme();
    const isDark = theme === 'dark';

    return (
        <button
            type="button"
            onClick={toggleTheme}
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Light mode' : 'Dark mode'}
            className="sl-theme-toggle"
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 32,
                height: 32,
                padding: 0,
                borderRadius: 4,
                border: '1px solid var(--t-border)',
                background: 'var(--t-panel-2)',
                color: 'var(--t-text-2)',
                cursor: 'pointer',
                flexShrink: 0,
            }}
        >
            <FontAwesomeIcon icon={isDark ? faSun : faMoon} style={{ width: 16, height: 16 }} aria-hidden />
        </button>
    );
}
