'use client';

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Chrome, DASHBOARD_V2_TABS, fmt } from './atoms';
import { useTelemetry } from './useTelemetry';
import { ConnectionPill, useTickingNow, V1Link, fmtAltitudeM, fmtPressure } from './shared';
import {
    buildNullschoolWindUrl,
    NULLSCHOOL_HOME,
    NULLSCHOOL_PRESSURE_LEVELS,
    NULLSCHOOL_ZOOM,
    pressureHpaToNullschoolLevel,
    type NullschoolPressureId,
} from '@/lib/wind/nullschool';
import WindDriftPanel from './WindDriftPanel';
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
    } = useTelemetry({ initialSelectedId });

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
    const [nsZoom, setNsZoom] = useState<number>(NULLSCHOOL_ZOOM.regional);
    const [forecastHours, setForecastHours] = useState(24);
    const [useLive, setUseLive] = useState(true);
    const [iframeBlocked, setIframeBlocked] = useState(false);

    useEffect(() => {
        if (latest?.pres != null) setLevel(suggestedLevel);
    }, [suggestedLevel, latest?.pres]);

    const center = useMemo(() => {
        if (lastFixRow?.lat != null && lastFixRow?.lon != null) {
            return { lat: lastFixRow.lat, lon: lastFixRow.lon };
        }
        const d = devices.find((x) => x.id === selectedId);
        if (d?.launchLat != null && d?.launchLon != null) {
            return { lat: d.launchLat, lon: d.launchLon };
        }
        return { lat: 37.73, lon: -122.43 };
    }, [lastFixRow, devices, selectedId]);

    const pressureHpa = latest?.pres ?? 250;

    const observedTrack: V2FlightPoint[] = useMemo(
        () =>
            rows
                .filter((r) => r.lat != null && r.lon != null)
                .map((r) => ({ lat: r.lat!, lon: r.lon!, t: r.t })),
        [rows],
    );

    const mapUrl = useMemo(
        () =>
            buildNullschoolWindUrl({
                lat: center.lat,
                lon: center.lon,
                level,
                zoom: nsZoom,
                at: useLive ? null : lastFixRow?.t ? new Date(lastFixRow.t) : null,
            }),
        [center, level, nsZoom, useLive, lastFixRow?.t],
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

    const onIframeError = useCallback(() => setIframeBlocked(true), []);

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
                    <input type="checkbox" checked={useLive} onChange={(e) => setUseLive(e.target.checked)} />
                    Live winds (nullschool)
                </label>

                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)', fontFamily: 'var(--sl-mono)' }}>
                        {lastFixRow
                            ? `${lastFixRow.lat!.toFixed(2)}°, ${lastFixRow.lon!.toFixed(2)}° · ${fmtAltitudeM(lastFixRow.alt)} · ${fmtPressure(latest?.pres)}`
                            : 'No GPS fix'}
                    </span>
                    <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={openBtnStyle}>
                        Open nullschool ↗
                    </a>
                </div>
            </div>

            <div
                style={{
                    flex: 1,
                    minHeight: 0,
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 0,
                }}
            >
                {/* Primary: our interactive drift forecast */}
                <div style={{ minWidth: 0, minHeight: 0, borderRight: '1px solid var(--sl-border)' }}>
                    <WindDriftPanel
                        startLat={center.lat}
                        startLon={center.lon}
                        pressureHpa={pressureHpa}
                        observedTrack={observedTrack}
                        forecastHours={forecastHours}
                    />
                </div>

                {/* Secondary: nullschool reference (pan/zoom in new tab recommended) */}
                <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                    <div
                        style={{
                            padding: '8px 12px',
                            borderBottom: '1px solid var(--sl-border)',
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: 8,
                            alignItems: 'center',
                        }}
                    >
                        <span style={{ fontSize: 11, color: 'var(--sl-text-dim)' }}>nullschool reference</span>
                        <button type="button" style={zoomBtnStyle} onClick={() => setNsZoom(NULLSCHOOL_ZOOM.continental)}>
                            Wide
                        </button>
                        <button type="button" style={zoomBtnStyle} onClick={() => setNsZoom(NULLSCHOOL_ZOOM.regional)}>
                            Regional
                        </button>
                        <button type="button" style={zoomBtnStyle} onClick={() => setNsZoom(NULLSCHOOL_ZOOM.local)}>
                            Local
                        </button>
                        <span style={{ fontSize: 10, color: 'var(--sl-text-dim3)' }}>
                            Embed is read-only — use Open nullschool for full pan/zoom
                        </span>
                    </div>
                    <div style={{ flex: 1, minHeight: 0, position: 'relative', background: '#000' }}>
                        {iframeBlocked ? (
                            <div style={iframeFallbackStyle}>
                                <p style={{ color: 'var(--sl-text)', maxWidth: 360, lineHeight: 1.55 }}>
                                    Open nullschool for interactive wind exploration at this pressure level.
                                </p>
                                <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={openBtnStyle}>
                                    Open earth.nullschool.net ↗
                                </a>
                            </div>
                        ) : (
                            <iframe
                                key={mapUrl}
                                title="earth.nullschool.net wind reference"
                                src={mapUrl}
                                style={{ border: 0, width: '100%', height: '100%' }}
                            />
                        )}
                        <div className="sl-wind-credit" style={creditStyle}>
                            <a href={NULLSCHOOL_HOME} target="_blank" rel="noopener noreferrer">
                                earth.nullschool.net
                            </a>
                            {useLive ? ' · live GFS' : lastFixRow ? ` · ${fmt.datetime(lastFixRow.t)}` : ''}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

const toolbarStyle: CSSProperties = {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    padding: '10px 20px',
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

const openBtnStyle: CSSProperties = {
    display: 'inline-block',
    padding: '6px 12px',
    fontSize: 11,
    fontWeight: 500,
    color: 'var(--sl-bg)',
    background: 'var(--sl-ok)',
    borderRadius: 4,
    textDecoration: 'none',
    whiteSpace: 'nowrap',
};

const zoomBtnStyle: CSSProperties = {
    fontSize: 10,
    padding: '4px 8px',
    background: 'var(--sl-bg-2)',
    border: '1px solid var(--sl-border)',
    color: 'var(--sl-text-dim)',
    borderRadius: 4,
    cursor: 'pointer',
};

const creditStyle: CSSProperties = {
    position: 'absolute',
    bottom: 8,
    left: 8,
    fontSize: 10,
    color: 'var(--sl-text-dim3)',
    background: 'rgba(11, 14, 19, 0.85)',
    padding: '4px 8px',
    borderRadius: 4,
};

const iframeFallbackStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    gap: 16,
    padding: 24,
    textAlign: 'center',
};
