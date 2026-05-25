'use client';

import { Suspense } from 'react';
import { useParams } from 'next/navigation';
import FlightReplayScreen from '@/components/dashboard-v2/FlightReplay';

function FlightReplayInner() {
    const params = useParams();
    const raw = params?.flightId;
    /* useParams already URL-decodes; just coerce array/undefined to a string. */
    const flightId = Array.isArray(raw) ? raw[0] : raw ?? '';
    return <FlightReplayScreen flightId={flightId} />;
}

export default function FlightReplayPage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <FlightReplayInner />
        </Suspense>
    );
}
