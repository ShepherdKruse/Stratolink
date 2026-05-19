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
    pressureHpaToNullschoolLevel,
    type NullschoolPressureId,
} from '@/lib/wind/nullschool';

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

    const mapUrl = useMemo(
        () =>
            buildNullschoolWindUrl({
                lat: center.lat,
                lon: center.lon,
                level,
                zoom: 4,
                at: useLive ? null : lastFixRow?.t ? new Date(lastFixRow.t) : null,
            }),
        [center, level, useLive, lastFixRow?.t],
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

            <div
                className="sl-wind-toolbar"
                style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 20px',
                    borderBottom: '1px solid var(--sl-border)',
                    flexShrink: 0,
                }}
            >
                <label style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    Device{' '}
                    <select
                        className="sl-wind-select"
                        value={selectedId ?? ''}
                        onChange={(e) => handleSelectDevice(e.target.value)}
                        style={selectStyle}
                    >
                        {devices.length === 0 && <option value="">—</option>}
                        {devices.map((d) => (
                            <option key={d.id} value={d.id}>
                                {d.callsign ?? d.id}
                            </option>
                        ))}
                    </select>
                </label>

                <label style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    Pressure band{' '}
                    <select
                        className="sl-wind-select"
                        value={level}
                        onChange={(e) => setLevel(e.target.value as NullschoolPressureId)}
                        style={selectStyle}
                    >
                        {NULLSCHOOL_PRESSURE_LEVELS.map((l) => (
                            <option key={l.id} value={l.id}>
                                {l.label} (~{Math.round(l.approxAltM / 1000)} km)
                            </option>
                        ))}
                    </select>
                </label>

                <label
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontSize: 11,
                        color: 'var(--sl-text-dim)',
                        cursor: 'pointer',
                    }}
                >
                    <input
                        type="checkbox"
                        checked={useLive}
                        onChange={(e) => setUseLive(e.target.checked)}
                    />
                    Live model (current winds)
                </label>

                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)', fontFamily: 'var(--sl-mono)' }}>
                        {lastFixRow
                            ? `${lastFixRow.lat!.toFixed(2)}°, ${lastFixRow.lon!.toFixed(2)}° · ${fmtAltitudeM(lastFixRow.alt)} · ${fmtPressure(latest?.pres)}`
                            : 'No GPS fix — using launch or default center'}
                    </span>
                    <a
                        href={mapUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="sl-wind-open-btn"
                        style={openBtnStyle}
                    >
                        Open full map ↗
                    </a>
                </div>
            </div>

            <div style={{ flex: 1, minHeight: 0, position: 'relative', background: '#0b0e13' }}>
                {iframeBlocked ? (
                    <div
                        style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            height: '100%',
                            gap: 16,
                            padding: 32,
                            textAlign: 'center',
                        }}
                    >
                        <p style={{ color: 'var(--sl-text)', maxWidth: 420, lineHeight: 1.6 }}>
                            The wind map cannot be embedded here (browser or site policy). Open it in a
                            new tab — we&apos;ll center it on your balloon and the pressure level you
                            selected.
                        </p>
                        <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={openBtnStyle}>
                            Open earth.nullschool.net ↗
                        </a>
                    </div>
                ) : (
                    <iframe
                        key={mapUrl}
                        title="Global wind at isobaric pressure — earth.nullschool.net"
                        src={mapUrl}
                        style={{ border: 0, width: '100%', height: '100%' }}
                        allowFullScreen
                        onError={onIframeError}
                    />
                )}

                <div className="sl-wind-credit" style={creditStyle}>
                    Wind data via{' '}
                    <a href={NULLSCHOOL_HOME} target="_blank" rel="noopener noreferrer">
                        earth.nullschool.net
                    </a>
                    {useLive ? ' · live' : lastFixRow ? ` · ${fmt.datetime(lastFixRow.t)} UTC` : ''}
                    {!useLive && (
                        <span style={{ color: 'var(--sl-text-dim3)' }}>
                            {' '}
                            (historical snapshot at last fix)
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

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

const creditStyle: CSSProperties = {
    position: 'absolute',
    bottom: 10,
    left: 12,
    fontSize: 10,
    color: 'var(--sl-text-dim3)',
    background: 'rgba(11, 14, 19, 0.85)',
    padding: '4px 8px',
    borderRadius: 4,
    pointerEvents: 'auto',
};
