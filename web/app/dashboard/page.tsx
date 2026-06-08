'use client';

import { Suspense } from 'react';
import MissionControlScreen from '@/components/dashboard-v2/MissionControl';

export default function DashboardPage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <MissionControlScreen />
        </Suspense>
    );
}
