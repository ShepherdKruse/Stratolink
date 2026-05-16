'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useIsMobile } from '@/hooks/use-mobile';
import MissionControlScreen from '@/components/dashboard-v2/MissionControl';
import MobileLayout from '@/components/mobile/MobileLayout';

function DashboardV2Switch() {
    const isMobile = useIsMobile();
    const searchParams = useSearchParams();
    const isPreview = searchParams.get('preview') === 'mobile';
    const balloonId = searchParams.get('device') ?? searchParams.get('balloon');

    if (isMobile || isPreview) {
        return <MobileLayout initialBalloonId={balloonId || null} />;
    }

    return <MissionControlScreen />;
}

export default function DashboardV2Page() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <DashboardV2Switch />
        </Suspense>
    );
}
