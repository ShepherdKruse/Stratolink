'use client';

import { Suspense } from 'react';
import MissionArchiveScreen from '@/components/dashboard-v2/MissionArchive';

export default function MissionArchivePage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <MissionArchiveScreen />
        </Suspense>
    );
}
