type PreferenceStorage = Pick<Storage, 'getItem' | 'setItem'>;

export function readLayerVisibility(storage: PreferenceStorage, layer: string, defaultVisible: boolean, previousLayers: string[] = []) {
    try {
        for (const name of [layer, ...previousLayers]) {
            const saved = storage.getItem(`stratolink-dashboard-${name}`);
            if (saved === 'true' || saved === 'false') return saved === 'true';
        }
    } catch { /* Keep the dashboard usable when storage is unavailable. */ }
    return defaultVisible;
}
