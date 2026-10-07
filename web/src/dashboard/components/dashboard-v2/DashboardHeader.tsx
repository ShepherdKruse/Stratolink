import { useCallback, useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faBars, faMoon, faSun, faXmark } from '@fortawesome/free-solid-svg-icons';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import { useCommunity } from './community-account';
import { useDashboardTheme } from './dashboard-theme';
import { useDashboardControls } from './dashboard-controls';

export default function DashboardHeader({ onBack }: { onBack?: (animate?: boolean) => void }) {
    const community = useCommunity();
    const { theme, setTheme } = useDashboardTheme();
    const controls = useDashboardControls(Boolean(onBack));
    const menuId = useId();
    const themeName = useId();
    const trigger = useRef<HTMLButtonElement>(null);
    const menu = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    const registrationOpen = community.panel === 'register';
    const [position, setPosition] = useState({ top: 64, right: 16 });

    const positionMenu = useCallback(() => {
        const bounds = trigger.current?.getBoundingClientRect();
        if (bounds) setPosition({ top: bounds.bottom + 10, right: Math.max(12, window.innerWidth - bounds.right) });
    }, []);

    useEffect(() => {
        if (!open) return;
        window.addEventListener('resize', positionMenu);
        window.addEventListener('scroll', positionMenu, true);
        return () => {
            window.removeEventListener('resize', positionMenu);
            window.removeEventListener('scroll', positionMenu, true);
        };
    }, [open, positionMenu]);

    return (
        <header className="dashboard-header">
            <div className="dashboard-header-row">
                <a href="/" target="_top" className="dashboard-home-link" aria-label="Stratolink home">
                    <img src="/assets/stratolink-wordmark.svg" alt="Stratolink" width={130} className="dashboard-wordmark" />
                </a>
                <div className="dashboard-header-actions">
                    <button type="button" className={`dashboard-register${registrationOpen ? ' is-close' : ''}`}
                        aria-label={registrationOpen ? 'Close registration' : !community.account ? 'Sign in with GitHub' : undefined}
                        aria-expanded={community.account ? registrationOpen : undefined}
                        aria-describedby={community.error ? 'github-signin-notice' : undefined}
                        disabled={community.loading || community.busy || community.activationLoading}
                        onClick={() => {
                            if (!community.account) { void community.signIn(); return; }
                            community.setPanel(registrationOpen ? null : 'register');
                        }}>
                        {registrationOpen ? <FontAwesomeIcon icon={faXmark} aria-hidden /> : community.account ? 'Register' : <>Sign in with <FontAwesomeIcon icon={faGithub} aria-hidden /></>}
                    </button>
                    {community.error && <span id="github-signin-notice" className="dashboard-signin-notice" role="status">{community.error}</span>}
                    <button
                        ref={trigger}
                        type="button"
                        className="dashboard-menu-trigger"
                        popoverTarget={menuId}
                        aria-label="Dashboard settings"
                        aria-haspopup="dialog"
                        aria-expanded={open}
                        aria-controls={menuId}
                    >
                        <FontAwesomeIcon icon={faBars} aria-hidden />
                    </button>
                </div>
            </div>
            {onBack && (
                <div className="dashboard-back-row">
                    <button type="button" className="dashboard-back" onClick={event => onBack(event.detail !== 0)}>
                        <FontAwesomeIcon icon={faChevronLeft} aria-hidden />
                        All balloons
                    </button>
                </div>
            )}
            <div
                ref={menu}
                id={menuId}
                popover="auto"
                role="dialog"
                aria-label="Dashboard settings"
                className="dashboard-menu"
                data-theme={theme}
                style={{ '--menu-top': `${position.top}px`, '--menu-right': `${position.right}px` } as CSSProperties}
                onBeforeToggle={(event) => {
                    if (event.newState === 'open') positionMenu();
                }}
                onToggle={(event) => {
                    const isOpen = event.newState === 'open';
                    setOpen(isOpen);
                    if (!isOpen && (menu.current?.contains(document.activeElement) || document.activeElement === document.body)) {
                        trigger.current?.focus({ preventScroll: true });
                    }
                }}
            >
                <fieldset className="dashboard-menu-group">
                    <legend>Appearance</legend>
                    <div className="dashboard-theme-choices">
                        <label className="dashboard-theme-choice">
                            <input type="radio" name={themeName} value="light" checked={theme === 'light'} onChange={() => setTheme('light')} />
                            <FontAwesomeIcon icon={faSun} aria-hidden />
                            Light
                        </label>
                        <label className="dashboard-theme-choice">
                            <input type="radio" name={themeName} value="dark" checked={theme === 'dark'} onChange={() => setTheme('dark')} />
                            <FontAwesomeIcon icon={faMoon} aria-hidden />
                            Dark
                        </label>
                    </div>
                </fieldset>
                <fieldset className="dashboard-menu-group dashboard-layer-options">
                    <legend>Map layers</legend>
                    <label className="dashboard-layer-option">
                        Gateway coverage
                        <input type="checkbox" role="switch" checked={controls.showGateways} onChange={(event) => controls.setShowGateways(event.target.checked)} />
                        <span className="dashboard-switch-track" aria-hidden />
                    </label>
                    {onBack && <label className="dashboard-layer-option">
                        Receiving ground stations
                        <input type="checkbox" role="switch" checked={controls.showReceivingStations} onChange={event => controls.setShowReceivingStations(event.target.checked)} />
                        <span className="dashboard-switch-track" aria-hidden />
                    </label>}
                    <label className="dashboard-layer-option">
                        Day and night
                        <input type="checkbox" role="switch" checked={controls.showDayNight} onChange={(event) => controls.setShowDayNight(event.target.checked)} />
                        <span className="dashboard-switch-track" aria-hidden />
                    </label>
                    <label className="dashboard-layer-option">
                        {onBack ? 'Flight paths' : 'Flight tails'}
                        <input type="checkbox" role="switch" checked={controls.showFlightTrail} onChange={(event) => controls.setShowFlightTrail(event.target.checked)} />
                        <span className="dashboard-switch-track" aria-hidden />
                    </label>
                    <label className="dashboard-layer-option">
                        Projected path
                        <input type="checkbox" role="switch" checked={controls.showProjectedPath} onChange={event => controls.setShowProjectedPath(event.target.checked)} />
                        <span className="dashboard-switch-track" aria-hidden />
                    </label>
                </fieldset>
                {community.account && <fieldset className="dashboard-menu-group dashboard-account-options"><legend><span>Manage</span><span className="dashboard-account-name"><FontAwesomeIcon icon={faGithub} aria-hidden /> @{community.account}</span></legend>
                    <button onClick={() => { menu.current?.hidePopover(); community.setPanel('manage'); }}>Your balloons</button>
                    <button className="dashboard-signout" disabled={community.busy} onClick={() => { menu.current?.hidePopover(); void community.signOut(); }}>Sign out</button>
                </fieldset>}
            </div>
        </header>
    );
}
