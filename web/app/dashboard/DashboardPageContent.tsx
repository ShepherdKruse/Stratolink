'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect } from 'react';
import { useIsMobile } from '@/hooks/use-mobile';
import DashboardClient from '@/components/dashboard/DashboardClient';
import MobileLayout from '@/components/mobile/MobileLayout';

export default function DashboardPageContent() {
    const isMobile = useIsMobile();
    const searchParams = useSearchParams();
    const mode = searchParams.get('mode');
    const balloonId = searchParams.get('balloon');

    // Split architecture: Mobile vs Desktop
    if (isMobile) {
        return <MobileLayout initialBalloonId={balloonId || null} />;
    }

    return <DashboardClient initialBalloonId={balloonId || null} initialMode={mode || null} />;
}
