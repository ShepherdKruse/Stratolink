'use client';

import { Suspense } from 'react';
import DashboardPageContent from './DashboardPageContent';

export default function DashboardPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-[#1a1a1a]" />}>
            <DashboardPageContent />
        </Suspense>
    );
}
