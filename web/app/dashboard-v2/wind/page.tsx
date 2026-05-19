'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useIsMobile } from '@/hooks/use-mobile';
import WindOutlookScreen from '@/components/dashboard-v2/WindOutlook';
import MobileLayout from '@/components/mobile/MobileLayout';

function WindOutlookSwitch() {
    const isMobile = useIsMobile();
    const searchParams = useSearchParams();
    const isPreview = searchParams.get('preview') === 'mobile';
    const balloonId = searchParams.get('device') ?? searchParams.get('balloon');

    if (isMobile || isPreview) {
        return <MobileLayout initialBalloonId={balloonId || null} />;
    }

    return <WindOutlookScreen />;
}

export default function WindOutlookPage() {
    return (
        <Suspense
            fallback={
                <div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading wind outlook…</div>
            }
        >
            <WindOutlookSwitch />
        </Suspense>
    );
}
