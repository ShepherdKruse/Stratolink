import { createRoot } from 'react-dom/client';
import { config } from '@fortawesome/fontawesome-svg-core';
import '@fortawesome/fontawesome-svg-core/styles.css';
import MissionControlScreen from './components/dashboard-v2/MissionControl';
import { DashboardThemeProvider } from './components/dashboard-v2/dashboard-theme';
import { DashboardControlsProvider } from './components/dashboard-v2/dashboard-controls';
import { GlobePortalProvider } from './components/dashboard-v2/globe-portal';
import { CommunityProvider } from './components/dashboard-v2/community-account';
import { finishOAuthRedirect } from './lib/community/auth';
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

// Restore the selected balloon before its first render. The provider displays any auth error.
void finishOAuthRedirect().catch(() => {}).then(renderDashboard);
