'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useIsMobile } from '@/hooks/use-mobile';
import TelemetryLabScreen from '@/components/dashboard-v2/TelemetryLab';
import MobileLayout from '@/components/mobile/MobileLayout';

function TelemetryLabSwitch() {
    const isMobile = useIsMobile();
    const searchParams = useSearchParams();
    const isPreview = searchParams.get('preview') === 'mobile';
    const balloonId = searchParams.get('device') ?? searchParams.get('balloon');

    /* Telemetry Lab is a desktop power-user view. On phones, fall back to the
     * mobile dashboard so the link doesn't dump people into a horizontally
     * scrolling chart workbench. */
    if (isMobile || isPreview) {
        return <MobileLayout initialBalloonId={balloonId || null} />;
    }

    return <TelemetryLabScreen />;
}

export default function TelemetryLabPage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <TelemetryLabSwitch />
        </Suspense>
    );
}
