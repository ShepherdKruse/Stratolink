'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import MobileRadar from './MobileRadar';
import type { MobileFleetDeviceRow } from './mobileStratolinkUtils';
import { fmtCoords, formatAge } from './mobileStratolinkUtils';
import { parseGateways } from './mobileGatewayGeo';
import { useForecastPath } from '../dashboard-v2/useForecastPath';

interface MobileMapLiveTabProps {
    balloonData: MobileFleetDeviceRow[];
    flightPathData: Array<{ lat: number; lon: number; time: Date }>;
    telemetryRows: Array<Record<string, unknown>>;
    selectedBalloonId: string | null;
    onSelectDevice: (id: string | null) => void;
    latestRow: Record<string, unknown> | undefined;
}

function coerceNum(v: unknown): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

type TimedPoint = { lon: number; lat: number; t: number };

/** Position [lon, lat] along a time-stamped track at time t (linear interp). */
function lerpTrack(track: TimedPoint[], t: number): [number, number] | null {
    if (track.length === 0) return null;
    if (t <= track[0].t) return [track[0].lon, track[0].lat];
    const last = track[track.length - 1];
    if (t >= last.t) return [last.lon, last.lat];
    for (let i = 1; i < track.length; i++) {
        const a = track[i - 1];
        const b = track[i];
        if (t <= b.t) {
            const f = (t - a.t) / ((b.t - a.t) || 1);
            return [a.lon + (b.lon - a.lon) * f, a.lat + (b.lat - a.lat) * f];
        }
    }
    return [last.lon, last.lat];
}

/** Position along the evenly-time-spaced nominal forecast path at time t. */
function nominalAt(path: Array<[number, number]>, originT: number, endT: number, t: number): [number, number] | null {
    if (path.length < 2 || endT <= originT) return null;
    const f = Math.max(0, Math.min(1, (t - originT) / (endT - originT)));
    const idx = f * (path.length - 1);
    const i = Math.floor(idx);
    const frac = idx - i;
    const a = path[i];
    const b = path[Math.min(i + 1, path.length - 1)];
    return [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac];
}

/** Compact UTC clock without seconds, e.g. "05-29 18:55". */
function fmtClock(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/** Map tab: Mapbox radar + forecast layers + a time scrubber above the tab bar. */
export default function MobileMapLiveTab({
    balloonData,
    flightPathData,
    telemetryRows,
    selectedBalloonId,
    onSelectDevice,
    latestRow,
}: MobileMapLiveTabProps) {
    const sel = balloonData.find((b) => b.id === selectedBalloonId);
    const forecast = useForecastPath(selectedBalloonId);

    const [scrubT, setScrubT] = useState<number | null>(null);
    /* Reset to live whenever the monitored balloon changes. */
    useEffect(() => { setScrubT(null); }, [selectedBalloonId]);

    /* GPS track (for balloon interpolation), chronological. */
    const trackPoints = useMemo<TimedPoint[]>(
        () => flightPathData
            .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon))
            .map((p) => ({ lon: p.lon, lat: p.lat, t: p.time.getTime() }))
            .sort((a, b) => a.t - b.t),
        [flightPathData],
    );

    /* Packet times (full span incl. no-GPS rows) for the timeline. */
    const rowTimes = useMemo<number[]>(
        () => telemetryRows
            .map((r) => new Date(String(r.time)).getTime())
            .filter((t) => Number.isFinite(t))
            .sort((a, b) => a - b),
        [telemetryRows],
    );

    const tStart = rowTimes[0] ?? trackPoints[0]?.t ?? null;
    const packetEndT = rowTimes[rowTimes.length - 1] ?? trackPoints[trackPoints.length - 1]?.t ?? null;
    const followLive = scrubT === null;
    const effectiveScrubT = followLive ? packetEndT : scrubT;
    const isFuture = effectiveScrubT !== null && packetEndT !== null && effectiveScrubT > packetEndT;

    /* Likely (reconstructed) track with even time spacing across the flight. */
    const hindcastTrack = useMemo<TimedPoint[]>(() => {
        const pts = forecast.hindcastPath;
        if (pts.length < 2 || trackPoints.length === 0) return [];
        const t0 = trackPoints[0].t;
        const t1 = trackPoints[trackPoints.length - 1].t;
        const span = t1 - t0 || 1;
        return pts.map(([lon, lat], i) => ({ lon, lat, t: t0 + (i / (pts.length - 1)) * span }));
    }, [forecast.hindcastPath, trackPoints]);

    /* Balloon position: forecast path in the future, likely path in the past. */
    const balloonOverride = useMemo<{ lat: number; lon: number } | null>(() => {
        if (effectiveScrubT === null) return null;
        if (isFuture && forecast.originT !== null && forecast.endT !== null) {
            const p = nominalAt(forecast.path, forecast.originT, forecast.endT, effectiveScrubT);
            return p ? { lon: p[0], lat: p[1] } : null;
        }
        const track = hindcastTrack.length >= 2 ? hindcastTrack : trackPoints;
        const p = lerpTrack(track, effectiveScrubT);
        return p ? { lon: p[0], lat: p[1] } : null;
    }, [effectiveScrubT, isFuture, forecast.path, forecast.originT, forecast.endT, hindcastTrack, trackPoints]);

    /* Telemetry row at/just before the scrub time, for the vitals readout. */
    const scrubRow = useMemo<Record<string, unknown> | undefined>(() => {
        if (effectiveScrubT === null || telemetryRows.length === 0) return latestRow;
        let row = telemetryRows[0];
        for (const r of telemetryRows) {
            const t = new Date(String(r.time)).getTime();
            if (Number.isFinite(t) && t <= effectiveScrubT) row = r;
            else break;
        }
        return row;
    }, [telemetryRows, effectiveScrubT, latestRow]);

    /* Show the forecast at the live edge and into the future; hide in the past. */
    const showForecast = effectiveScrubT !== null && packetEndT !== null && effectiveScrubT >= packetEndT;

    const mapGateways = isFuture ? null : parseGateways(scrubRow?.gateways);
    const rssi = coerceNum(scrubRow?.rssi) ?? (sel?.rssi != null ? sel.rssi : null);
    const satsRaw = coerceNum(scrubRow?.gps_satellites) ?? (sel?.gps_satellites ?? null);
    const battVolts = coerceNum(scrubRow?.battery_voltage) ?? coerceNum(sel?.battery_voltage ?? null);
    const alt = coerceNum(scrubRow?.altitude_m) ?? (sel && !sel.awaiting_gps ? sel.altitude_m : null);
    const liveIso = sel?.last_contact ?? null;

    const tabBarReserve = `calc(3.25rem + max(34px, env(safe-area-inset-bottom)))`;
    const hasTimeline = tStart !== null && packetEndT !== null && packetEndT > tStart;

    return (
        <div className="relative h-full w-full">
            <div className="absolute inset-0 z-0">
                <MobileRadar
                    balloonData={balloonData}
                    flightPathData={selectedBalloonId ? flightPathData : []}
                    onBalloonClick={(id) => onSelectDevice(id)}
                    selectedBalloonId={selectedBalloonId}
                    gateways={mapGateways}
                    playbackT={isFuture ? null : effectiveScrubT}
                    balloonOverride={balloonOverride}
                    showTransmitPoints={!!selectedBalloonId}
                    forecastPath={showForecast ? forecast.path : []}
                    forecastEnsemble={showForecast ? forecast.ensemble : []}
                    forecastEllipses={showForecast ? forecast.ellipses : []}
                    hindcastPath={selectedBalloonId ? forecast.hindcastPath : []}
                    staleLine={staleLineFor(forecast, trackPoints)}
                />
            </div>

            <div
                className="pointer-events-none absolute left-4 right-4 z-40 flex items-start gap-2"
                style={{ top: `max(12px, env(safe-area-inset-top))` }}>
                <div
                    className="pointer-events-auto flex min-h-[48px] min-w-0 flex-1 items-center gap-[10px] border px-4 py-2"
                    style={{ background: 'rgba(11, 14, 19, 0.78)', borderColor: 'var(--border-hi)', backdropFilter: 'blur(20px)' }}>
                    <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-[var(--ok)]" />
                    <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-[13px] font-medium" style={{ color: 'var(--text-hi)' }}>
                            {selectedBalloonId ?? 'Tap marker'}
                        </div>
                        <div className="truncate font-mono text-[10px]" style={{ color: 'var(--text-dim2)' }}>
                            {sel ? fmtCoords(sel.lat, sel.lon) : 'Fleet overview'}
                        </div>
                    </div>
                    {selectedBalloonId ? (
                        <button
                            type="button"
                            aria-label="Clear selection"
                            onClick={() => onSelectDevice(null)}
                            className="pointer-events-auto shrink-0 bg-transparent px-1 font-mono text-[17px]"
                            style={{ color: 'var(--text-dim)', lineHeight: 1 }}>
                            ×
                        </button>
                    ) : null}
                </div>
            </div>

            <div
                className="absolute left-0 right-0 z-[35] border-t"
                style={{
                    bottom: tabBarReserve,
                    background: 'rgba(11, 14, 19, 0.88)',
                    borderColor: 'var(--border-hi)',
                    backdropFilter: 'blur(24px)',
                }}>
                <div className="flex justify-center pt-3 pb-1">
                    <div className="h-1 w-9 rounded bg-[var(--text-dim3)]" />
                </div>
                <div className="px-5 pb-5">
                    {selectedBalloonId && hasTimeline ? (
                        <Scrubber
                            tStart={tStart!}
                            packetEndT={packetEndT!}
                            futureEndT={forecast.endT}
                            scrubT={scrubT}
                            onScrub={setScrubT}
                        />
                    ) : null}
                    <div className="mb-4 mt-1 flex justify-between gap-2">
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>
                            {followLive ? 'Live vitals' : isFuture ? 'Forecast' : 'At scrub'}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: 'var(--text-dim3)' }}>
                            {followLive
                                ? `uplink ${formatAge(liveIso)}`
                                : effectiveScrubT !== null ? fmtClock(effectiveScrubT) : ''}
                        </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
                        <VitalsUnit label="Alt" value={typeof alt === 'number' && Number.isFinite(alt) ? String(Math.round(alt)) : '—'} suf="m" />
                        <VitalsUnit label="Batt" value={battVolts != null ? battVolts.toFixed(2) : '—'} suf="V" />
                        <VitalsUnit label="RSSI" value={rssi != null ? String(Math.round(rssi)) : '—'} suf="dBm" />
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--text-dim2)' }}>
                                Sats
                            </div>
                            <div
                                className="font-mono text-[14px] font-medium"
                                style={{
                                    marginTop: 4,
                                    color: typeof satsRaw === 'number' && satsRaw > 0 ? 'var(--text-hi)' : 'var(--alert)',
                                    fontVariantNumeric: 'tabular-nums',
                                }}>
                                {satsRaw ?? '—'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

/** Gray connector from last fix → dead-reckoned now, when GPS is stale. */
function staleLineFor(
    forecast: ReturnType<typeof useForecastPath>,
    trackPoints: TimedPoint[],
): Array<[number, number]> | null {
    if (!forecast.staleGps) return null;
    /* Prefer the wind-integrated predicted-hindcast curve; fall back to a
     * straight last-fix→now connector for older forecasts. */
    if (forecast.predictedHindcast.length >= 2) return forecast.predictedHindcast;
    if (forecast.path.length === 0 || trackPoints.length === 0) return null;
    const last = trackPoints[trackPoints.length - 1];
    return [[last.lon, last.lat], forecast.path[0]];
}

/* ──────────────────────────────────────────────────────────────
 * Touch scrubber — drag to move through time; extends into the
 * forecast horizon. Snap to the "now" boundary re-arms follow-live.
 * ────────────────────────────────────────────────────────────── */
function Scrubber({ tStart, packetEndT, futureEndT, scrubT, onScrub }: {
    tStart: number;
    packetEndT: number;
    futureEndT: number | null;
    scrubT: number | null;
    onScrub: (t: number | null) => void;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    const tEnd = futureEndT !== null && futureEndT > packetEndT ? futureEndT : packetEndT;
    const span = tEnd - tStart || 1;
    const hasFuture = tEnd > packetEndT;
    const pct = (t: number) => Math.max(0, Math.min(100, ((t - tStart) / span) * 100));
    const nowFrac = pct(packetEndT);
    const cursorT = scrubT ?? packetEndT;
    const fraction = pct(cursorT);
    const elapsedW = Math.min(fraction, nowFrac);

    function pickFromClientX(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const t = tStart + span * f;
        if (Math.abs(t - packetEndT) <= span * 0.02) { onScrub(null); return; }
        onScrub(t);
    }

    return (
        <div className="mb-3">
            <div className="mb-1.5 flex justify-between font-mono text-[10px]" style={{ color: 'var(--text-dim3)' }}>
                <span>{fmtClock(tStart)}</span>
                <span style={{ color: cursorT > packetEndT ? '#f59e0b' : 'var(--ok)' }}>{fmtClock(cursorT)}</span>
                <span>{fmtClock(tEnd)}</span>
            </div>
            <div
                ref={trackRef}
                role="slider"
                aria-valuemin={tStart}
                aria-valuemax={tEnd}
                aria-valuenow={cursorT}
                tabIndex={0}
                onPointerDown={(e) => {
                    e.currentTarget.setPointerCapture(e.pointerId);
                    pickFromClientX(e.clientX);
                }}
                onPointerMove={(e) => {
                    if (e.buttons === 0 && e.pressure === 0) return;
                    pickFromClientX(e.clientX);
                }}
                style={{ position: 'relative', height: 28, cursor: 'pointer', touchAction: 'none', userSelect: 'none' }}>
                {/* base track */}
                <div style={{ position: 'absolute', top: 13, left: 0, right: 0, height: 2, background: 'var(--border-hi)' }} />
                {/* future region */}
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 13, left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 2, background: 'rgba(245, 158, 11, 0.25)' }} />
                )}
                {/* elapsed */}
                <div style={{ position: 'absolute', top: 13, left: 0, width: `${elapsedW}%`, height: 2, background: 'var(--ok)' }} />
                {/* future progress */}
                {fraction > nowFrac && (
                    <div style={{ position: 'absolute', top: 13, left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 2, background: '#f59e0b' }} />
                )}
                {/* now divider */}
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 7, left: `calc(${nowFrac}% - 0.5px)`, width: 1, height: 14, background: 'var(--text-dim2)' }} />
                )}
                {/* handle */}
                <div style={{
                    position: 'absolute', top: 7, left: `calc(${fraction}% - 7px)`,
                    width: 14, height: 14, borderRadius: '50%',
                    background: cursorT > packetEndT ? '#f59e0b' : 'var(--ok)',
                    border: '2px solid rgba(11,14,19,0.9)',
                }} />
            </div>
        </div>
    );
}

function VitalsUnit({ label, value, suf }: { label: string; value: string; suf?: string }) {
    return (
        <div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--text-dim2)' }}>{label}</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, marginTop: 4, color: 'var(--text-hi)', fontVariantNumeric: 'tabular-nums' }}>
                {value}
                {suf ? <span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>{suf}</span> : null}
            </div>
        </div>
    );
}
