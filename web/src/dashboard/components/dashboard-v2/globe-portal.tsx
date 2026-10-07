import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type GlobeStage = 'standalone' | 'footer' | 'entering' | 'dashboard';
const GlobePortalContext = createContext<GlobeStage>('standalone');
export function notifyGlobeParent(type: string, detail: Record<string, unknown> = {}) {
    if (window.parent !== window) window.parent.postMessage({ channel: 'stratolink-globe', type, ...detail }, window.location.origin);
}
export function GlobePortalProvider({ children }: { children: ReactNode }) {
    const [stage, setStage] = useState<GlobeStage>(() => window.parent !== window && new URLSearchParams(location.search).get('portal') === 'footer' ? 'footer' : 'standalone');
    useEffect(() => {
        if (stage === 'standalone') return;
        document.documentElement.dataset.globePortal = stage;
        function receive(event: MessageEvent) {
            if (event.origin !== location.origin || event.source !== window.parent || event.data?.channel !== 'stratolink-globe') return;
            if (['footer', 'entering', 'dashboard'].includes(event.data.stage)) setStage(event.data.stage);
        }
        window.addEventListener('message', receive);
        return () => window.removeEventListener('message', receive);
    }, [stage]);
    return <GlobePortalContext.Provider value={stage}>{children}</GlobePortalContext.Provider>;
}
export function useGlobePortal() { return useContext(GlobePortalContext); }
