import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

type DashboardControls = {
    showReceivingStations: boolean;
    setShowReceivingStations: (visible: boolean) => void;
    showGateways: boolean;
    setShowGateways: (visible: boolean) => void;
    showDayNight: boolean;
    setShowDayNight: (visible: boolean) => void;
    fleetTails: boolean;
    setFleetTails: (visible: boolean) => void;
    fleetProjection: boolean;
    setFleetProjection: (visible: boolean) => void;
    detailPaths: boolean;
    setDetailPaths: (visible: boolean) => void;
    detailProjection: boolean;
    setDetailProjection: (visible: boolean) => void;
};

const DashboardControlsContext = createContext<DashboardControls | null>(null);

function useStoredVisibility(layer: string, defaultVisible = true) {
    const key = `stratolink-dashboard-${layer}`;
    const [visible, setVisible] = useState(() => {
        try {
            const saved = localStorage.getItem(key);
            return saved === null ? defaultVisible : saved === 'true';
        } catch {
            return defaultVisible;
        }
    });
    const update = useCallback((next: boolean) => {
        setVisible(next);
        try {
            localStorage.setItem(key, String(next));
        } catch {
            // Keep the current session usable when browser storage is unavailable.
        }
    }, [key]);
    return [visible, update] as const;
}

export function DashboardControlsProvider({ children }: { children: ReactNode }) {
    const [showReceivingStations, setShowReceivingStations] = useStoredVisibility('receiving-stations', false);
    const [showGateways, setShowGateways] = useStoredVisibility('gateways');
    const [showDayNight, setShowDayNight] = useStoredVisibility('day-night');
    const [fleetTails, setFleetTails] = useStoredVisibility('flight-tails', false);
    const [fleetProjection, setFleetProjection] = useStoredVisibility('fleet-projection', false);
    const [detailPaths, setDetailPaths] = useStoredVisibility('detail-paths');
    const [detailProjection, setDetailProjection] = useStoredVisibility('detail-projection');

    return (
        <DashboardControlsContext.Provider value={{
            showReceivingStations, setShowReceivingStations,
            showGateways, setShowGateways,
            showDayNight, setShowDayNight,
            fleetTails, setFleetTails, fleetProjection, setFleetProjection,
            detailPaths, setDetailPaths, detailProjection, setDetailProjection,
        }}>
            {children}
        </DashboardControlsContext.Provider>
    );
}

export function useDashboardControls(expanded = false) {
    const controls = useContext(DashboardControlsContext);
    if (!controls) throw new Error('useDashboardControls must be used within DashboardControlsProvider');
    return {
        showReceivingStations: expanded && controls.showReceivingStations, setShowReceivingStations: controls.setShowReceivingStations,
        showGateways: controls.showGateways, setShowGateways: controls.setShowGateways,
        showDayNight: controls.showDayNight, setShowDayNight: controls.setShowDayNight,
        showFlightTrail: expanded ? controls.detailPaths : controls.fleetTails,
        setShowFlightTrail: expanded ? controls.setDetailPaths : controls.setFleetTails,
        showProjectedPath: expanded ? controls.detailProjection : controls.fleetProjection,
        setShowProjectedPath: expanded ? controls.setDetailProjection : controls.setFleetProjection,
    };
}
