import { useCallback, useEffect, useRef, useState } from 'react';
import { Layer, Source } from 'react-map-gl/mapbox';
import type { Feature, FeatureCollection, LineString } from 'geojson';
import { forecastRequests } from '@/lib/telemetry/forecastRequests';
import { unwrapLngs } from '@/lib/telemetry/flightTail';
import { cleanPath } from './useForecastPath';

const EMPTY: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] };

/** One map source for the optional fleet layer; requests stop when it is hidden. */
export function FleetProjections({ deviceIds, color }: { deviceIds: string[]; color: string }) {
    const [data, setData] = useState(EMPTY);
    const entries = useRef(new Map<string, { stop?: () => void; feature?: Feature<LineString> }>());
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const publish = useCallback(() => {
        if (timer.current) return;
        timer.current = setTimeout(() => {
            timer.current = undefined;
            setData({ type: 'FeatureCollection', features: [...entries.current.values()].flatMap(entry => entry.feature ? [entry.feature] : []) });
        }, 100);
    }, []);
    const idsKey = JSON.stringify(deviceIds);
    useEffect(() => {
        const ids = new Set(JSON.parse(idsKey) as string[]);
        for (const [id, entry] of entries.current) {
            if (ids.has(id)) continue;
            entry.stop?.();
            entries.current.delete(id);
            if (entry.feature) publish();
        }
        for (const id of ids) {
            if (entries.current.has(id)) continue;
            const entry: { stop?: () => void; feature?: Feature<LineString> } = {};
            entries.current.set(id, entry);
            entry.stop = forecastRequests.watch(id, result => {
                if (result.status === 202) return;
                const coordinates = unwrapLngs(cleanPath(result.data?.nominal_path));
                if (coordinates.length < 2) {
                    if (!entry.feature) return;
                    entry.feature = undefined;
                } else {
                    if (entry.feature && JSON.stringify(entry.feature.geometry.coordinates) === JSON.stringify(coordinates)) return;
                    entry.feature = { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates } };
                }
                publish();
            }, false, 'path');
        }
    }, [idsKey, publish]);
    useEffect(() => () => {
        for (const entry of entries.current.values()) entry.stop?.();
        entries.current.clear();
        clearTimeout(timer.current);
        timer.current = undefined;
    }, []);
    if (!data.features.length) return null;
    return <Source id="v2-fleet-projections" type="geojson" data={data}>
        <Layer id="v2-fleet-projections-line" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': color, 'line-width': 2, 'line-opacity': 0.8, 'line-dasharray': [2, 3] }} />
    </Source>;
}
