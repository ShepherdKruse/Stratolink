import { createRoot } from 'react-dom/client';
import { config } from '@fortawesome/fontawesome-svg-core';
import '@fortawesome/fontawesome-svg-core/styles.css';
import MissionControlScreen from './components/dashboard-v2/MissionControl';
import { DashboardThemeProvider } from './components/dashboard-v2/dashboard-theme';
import { DashboardControlsProvider } from './components/dashboard-v2/dashboard-controls';
import { GlobePortalProvider } from './components/dashboard-v2/globe-portal';
import { CommunityProvider } from './components/dashboard-v2/community-account';
import { finishOAuthRedirect } from './lib/community/auth';
import { initializeOnboarding } from './lib/community/activation';
import './globals.css';
import './fonts.css';
import './styles/dashboard-v2.css';
import './styles/telemetry-v3-theme.css';
import './styles/header.css';
import './styles/fleet.css';
import './styles/globe-portal.css';
import './styles/community.css';

config.autoAddCss = false;

function renderDashboard() { createRoot(document.getElementById('dashboard-root')!).render(
    <GlobePortalProvider>
        <DashboardThemeProvider>
            <DashboardControlsProvider>
                <CommunityProvider><MissionControlScreen /></CommunityProvider>
            </DashboardControlsProvider>
        </DashboardThemeProvider>
    </GlobePortalProvider>,
); }

/* A chunk that fails to import (a deploy changed the hashed filenames under an open page, or a dev-server module
 * invalidation) would take the whole React tree down silently, which in the homepage footer means no globe.
 * Reload once: fresh HTML references the current chunks. */
const CHUNK_RETRY_KEY = 'stratolink-chunk-reload';
function recoverFromChunkFailure(reason: unknown) {
    const message = String((reason as { message?: unknown })?.message ?? reason ?? '');
    if (!/Importing a module script failed|Failed to fetch dynamically imported module|error loading dynamically imported module|Loading chunk/i.test(message)) return;
    let retried = false;
    try { retried = sessionStorage.getItem(CHUNK_RETRY_KEY) === location.href; sessionStorage.setItem(CHUNK_RETRY_KEY, location.href); } catch { /* storage optional */ }
    if (!retried) location.reload();
}
window.addEventListener('unhandledrejection', event => recoverFromChunkFailure(event.reason));
window.addEventListener('error', event => recoverFromChunkFailure(event.error ?? event.message));

// Restore the selected balloon before its first render. The provider displays any auth error.
void finishOAuthRedirect().catch(() => {}).then(() => {
    void initializeOnboarding().catch(() => {});
    renderDashboard();
});
