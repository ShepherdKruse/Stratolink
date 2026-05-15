import { Suspense } from 'react';
import DeviceTrackerScreen from '@/components/dashboard-v2/DeviceTracker';

export default function DeviceTrackerPage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <DeviceTrackerScreen />
        </Suspense>
    );
}
