import fs from 'fs';
import path from 'path';
import type { Metadata } from 'next';
import MissionOutreachClient from '@/components/mission-outreach/MissionOutreachClient';

export const metadata: Metadata = {
    title: 'Mission · USSF/JROTC outreach',
    description:
        'A functional mock satellite mission platform for Space Force outreach, JROTC programs, and SFA chapters — payload architecture, live ops dashboard, and program formats.',
    /* Unlisted outreach page — share via direct link only; not linked from the public site. */
    robots: { index: false, follow: false },
    openGraph: {
        title: 'Stratolink Mission · USSF/JROTC outreach',
        description:
            'Put a functioning atmospheric payload in students\' hands — sensor suite, telemetry uplink, and a mission operations dashboard they control.',
        url: '/mission',
    },
};

function loadMissionHtml(): string {
    const htmlPath = path.join(process.cwd(), 'content', 'mission-outreach.html');
    return fs.readFileSync(htmlPath, 'utf8');
}

export default function MissionPage() {
    const html = loadMissionHtml();
    return <MissionOutreachClient html={html} />;
}
