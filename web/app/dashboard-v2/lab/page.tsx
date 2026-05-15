import { Suspense } from 'react';
import TelemetryLabScreen from '@/components/dashboard-v2/TelemetryLab';

export default function TelemetryLabPage() {
    return (
        <Suspense fallback={<div style={{ padding: 24, color: 'var(--sl-text-dim2)' }}>Loading…</div>}>
            <TelemetryLabScreen />
        </Suspense>
    );
}
