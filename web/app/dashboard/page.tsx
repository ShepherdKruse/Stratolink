'use client';

import { useIsMobile } from '@/hooks/use-mobile';
import DashboardClient from '@/components/dashboard/DashboardClient';
import MobileLayout from '@/components/mobile/MobileLayout';

export default function DashboardPage() {
    const isMobile = useIsMobile();

    // Split architecture: Mobile vs Desktop
    if (isMobile) {
        return <MobileLayout />;
    }

    return <DashboardClient />;
}
