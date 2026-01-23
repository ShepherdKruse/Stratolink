'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect } from 'react';
import { useIsMobile } from '@/hooks/use-mobile';
import DashboardClient from '@/components/dashboard/DashboardClient';
import MobileLayout from '@/components/mobile/MobileLayout';
import { ErrorBoundary } from '@/components/ErrorBoundary';

export default function DashboardPageContent() {
    const isMobile = useIsMobile();
    const searchParams = useSearchParams();
    const mode = searchParams.get('mode');
    const balloonId = searchParams.get('balloon');
    const isPreview = searchParams.get('preview') === 'mobile';

    // Split architecture: Mobile vs Desktop
    // Force mobile view if preview mode (for showcase)
    if (isMobile || isPreview) {
        return (
            <ErrorBoundary>
                <MobileLayout initialBalloonId={balloonId || null} />
            </ErrorBoundary>
        );
    }

    return (
        <ErrorBoundary>
            <DashboardClient initialBalloonId={balloonId || null} initialMode={mode || null} />
        </ErrorBoundary>
    );
}
