import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { readLayerVisibility } from '@/lib/telemetry/dashboardPreferences';

type DashboardControls = {
    showReceivingStations: boolean;
    setShowReceivingStations: (visible: boolean) => void;
    showGateways: boolean;
    setShowGateways: (visible: boolean) => void;
    showDayNight: boolean;
    setShowDayNight: (visible: boolean) => void;
    showFlightTrail: boolean;
    setShowFlightTrail: (visible: boolean) => void;
    showProjectedPath: boolean;
    setShowProjectedPath: (visible: boolean) => void;
};

const DashboardControlsContext = createContext<DashboardControls | null>(null);

function useStoredVisibility(layer: string, defaultVisible = true, previousLayers: string[] = []) {
    const key = `stratolink-dashboard-${layer}`;
    const [visible, setVisible] = useState(() => {
        try {
            return readLayerVisibility(localStorage, layer, defaultVisible, previousLayers);
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
    const [showFlightTrail, setShowFlightTrail] = useStoredVisibility('flight-paths', false, ['flight-tails', 'detail-paths']);
    const [showProjectedPath, setShowProjectedPath] = useStoredVisibility('projected-path', false, ['fleet-projection', 'detail-projection']);

    return (
        <DashboardControlsContext.Provider value={{
            showReceivingStations, setShowReceivingStations,
            showGateways, setShowGateways,
            showDayNight, setShowDayNight,
            showFlightTrail, setShowFlightTrail, showProjectedPath, setShowProjectedPath,
        }}>
            {children}
        </DashboardControlsContext.Provider>
    );
}

export function useDashboardControls() {
    const controls = useContext(DashboardControlsContext);
    if (!controls) throw new Error('useDashboardControls must be used within DashboardControlsProvider');
    return controls;
}
