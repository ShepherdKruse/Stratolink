import { Suspense } from 'react';
import ActivateDeviceInner from './activate-device-inner';

export default function ActivatePageRoute({ params }: { params: Promise<{ deviceId: string }> }) {
    return (
        <Suspense
            fallback={
                <div className="min-h-screen bg-[#1a1a1a] flex items-center justify-center text-[#666] text-sm font-mono">
                    Loading…
                </div>
            }
        >
            <ActivateDeviceInner params={params} />
        </Suspense>
    );
}
