'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Chrome, DASHBOARD_V2_TABS } from './atoms';
import { useTelemetry } from './useTelemetry';
import { ConnectionPill, useTickingNow, V1Link } from './shared';
import {
    buildNullschoolWindUrl,
    NULLSCHOOL_PRESSURE_LEVELS,
    pressureHpaToNullschoolLevel,
    type NullschoolPressureId,
} from '@/lib/wind/nullschool';
import { snapPressureHpa } from '@/lib/wind/fetchWindGrid';
import WindSynthesisMap from './wind/WindSynthesisMap';
import type { V2FlightPoint } from './V2MissionMap';

export default function WindOutlookScreen() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const initialSelectedId = searchParams.get('device');
    const now = useTickingNow();

    const {
        devices,
        selectedId,
        setSelectedId,
        rows,
        deviceInfo,
        status,
        lastFetchedAt,
        loading,
    } = useTelemetry({ initialSelectedId });

    const selectedDevice = useMemo(
        () => devices.find((d) => d.id === selectedId) ?? null,
        [devices, selectedId],
    );

    const lastFixRow = useMemo(
        () => [...rows].reverse().find((r) => r.lat !== null && r.lon !== null) ?? null,
        [rows],
    );
    const latest = rows.length ? rows[rows.length - 1] : null;

    const suggestedLevel = useMemo(
        () => pressureHpaToNullschoolLevel(latest?.pres ?? null),
        [latest?.pres],
    );

    const [level, setLevel] = useState<NullschoolPressureId>('250hPa');
    const [forecastHours, setForecastHours] = useState(24);
    const [showWind, setShowWind] = useState(true);

    useEffect(() => {
        if (latest?.pres != null) setLevel(suggestedLevel);
    }, [suggestedLevel, latest?.pres]);

    const center = useMemo(() => {
        if (lastFixRow?.lat != null && lastFixRow?.lon != null) {
            return { lat: lastFixRow.lat, lon: lastFixRow.lon };
        }
        if (selectedDevice?.launchLat != null && selectedDevice?.launchLon != null) {
            return { lat: selectedDevice.launchLat, lon: selectedDevice.launchLon };
        }
        return { lat: 37.73, lon: -122.43 };
    }, [lastFixRow, selectedDevice]);

    const pressureHpa = latest?.pres ?? 250;
    const callsign = selectedDevice?.callsign ?? selectedDevice?.id ?? 'Balloon';

    const observedTrack: V2FlightPoint[] = useMemo(
        () =>
            rows
                .filter((r) => r.lat != null && r.lon != null)
                .map((r) => ({ lat: r.lat!, lon: r.lon!, t: r.t })),
        [rows],
    );

    const baroSamples = useMemo(
        () =>
            rows
                .filter((r) => r.alt != null && Number.isFinite(r.alt) && r.alt > 0)
                .map((r) => ({ time_utc: new Date(r.t).toISOString(), alt_m: r.alt as number })),
        [rows],
    );

    const forecastAnchorKey = useMemo(() => {
        const fixT = lastFixRow?.t ?? 0;
        const hpa = snapPressureHpa(latest?.pres ?? 250);
        return `${selectedId ?? ''}-${forecastHours}-${fixT}-${hpa}`;
    }, [selectedId, forecastHours, lastFixRow?.t, latest?.pres]);

    const mapUrl = useMemo(
        () =>
            buildNullschoolWindUrl({
                lat: center.lat,
                lon: center.lon,
                level,
                at: null,
            }),
        [center, level],
    );

    function handleNavigate(path: string) {
        const url = selectedId ? `${path}?device=${encodeURIComponent(selectedId)}` : path;
        router.push(url);
    }

    function handleSelectDevice(id: string) {
        setSelectedId(id);
        const params = new URLSearchParams(searchParams.toString());
        params.set('device', id);
        router.replace(`/dashboard-v2/wind?${params.toString()}`);
    }

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2/wind"
                onNavigate={handleNavigate}
                version={deviceInfo?.firmware ?? undefined}
                lastUplinkT={latest?.t ?? null}
                lastFixT={lastFixRow?.t ?? null}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={lastFetchedAt} now={now} />
                        <V1Link />
                    </>
                }
            />

            <div className="sl-wind-toolbar" style={toolbarStyle}>
                <label style={labelStyle}>
                    Device{' '}
                    <select value={selectedId ?? ''} onChange={(e) => handleSelectDevice(e.target.value)} style={selectStyle}>
                        {devices.map((d) => (
                            <option key={d.id} value={d.id}>
                                {d.callsign ?? d.id}
                            </option>
                        ))}
                    </select>
                </label>

                <label style={labelStyle}>
                    Pressure{' '}
                    <select
                        value={level}
                        onChange={(e) => setLevel(e.target.value as NullschoolPressureId)}
                        style={selectStyle}
                    >
                        {NULLSCHOOL_PRESSURE_LEVELS.map((l) => (
                            <option key={l.id} value={l.id}>
                                {l.label}
                            </option>
                        ))}
                    </select>
                </label>

                <label style={labelStyle}>
                    Forecast{' '}
                    <select
                        value={forecastHours}
                        onChange={(e) => setForecastHours(parseInt(e.target.value, 10))}
                        style={selectStyle}
                    >
                        <option value={12}>12 h</option>
                        <option value={24}>24 h</option>
                        <option value={48}>48 h</option>
                    </select>
                </label>

                <label style={{ ...labelStyle, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={showWind} onChange={(e) => setShowWind(e.target.checked)} />
                    Wind overlay
                </label>
            </div>

            <div style={{ flex: 1, minHeight: 0 }}>
                <WindSynthesisMap
                    deviceId={selectedId ?? callsign}
                    callsign={callsign}
                    observedTrack={observedTrack}
                    baroSamples={baroSamples}
                    startLat={center.lat}
                    startLon={center.lon}
                    launchLat={selectedDevice?.launchLat}
                    launchLon={selectedDevice?.launchLon}
                    pressureHpa={pressureHpa}
                    forecastHours={forecastHours}
                    showWind={showWind}
                    anchorKey={forecastAnchorKey}
                    telemetryReady={!loading && observedTrack.length > 0}
                    nullschoolUrl={mapUrl}
                    lastAltM={lastFixRow?.alt ?? null}
                />
            </div>
        </div>
    );
}

const toolbarStyle: CSSProperties = {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    padding: '8px 20px',
    borderBottom: '1px solid var(--sl-border)',
    flexShrink: 0,
};

const labelStyle: CSSProperties = { fontSize: 11, color: 'var(--sl-text-dim2)' };

const selectStyle: CSSProperties = {
    marginLeft: 6,
    background: 'var(--sl-bg-2)',
    color: 'var(--sl-text)',
    border: '1px solid var(--sl-border)',
    borderRadius: 4,
    padding: '4px 8px',
    fontSize: 12,
    fontFamily: 'var(--sl-mono)',
};
