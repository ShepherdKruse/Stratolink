/**
 * Mission Control — the single unified flight page.
 *
 * One page, three regions:
 *   - LEFT column: the monitored balloon (with a switcher) on top, then a
 *     synchronized stack of telemetry charts.
 *   - RIGHT: a Mapbox map showing gateway coverage and the balloon's flight in
 *     three states — transmitted points (dots), the flown path between them
 *     (line), and the predicted next track (dashed forecast).
 *   - BOTTOM: a full-width timeline. Scrubbing it rewinds BOTH the charts and
 *     the balloon's position on the map to the row recorded at that moment.
 *
 * Defaults to the most-recently-transmitting balloon. Selecting a landed
 * balloon replays its full mission (useTelemetry loads since-launch history).
 *
 * Data discipline: every value is a real Supabase row or '-'. No placeholders.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowRight, faChevronDown, faChevronUp } from '@fortawesome/free-solid-svg-icons';
import { Chart, fmt, type TelemetryRow } from './atoms';
import { useTelemetry, useFleetHistory, type DeviceSummary } from './useTelemetry';
import { useForecastPath, type UseForecastPathResult } from './useForecastPath';
import { useElementSize, fmtPressure, fmtAltitudeM } from './shared';
import { useIsMobile } from '@/hooks/use-mobile';
import type { V2Balloon, V2FlightPoint, V2Gateway } from './V2MissionMap';
import { useDashboardTheme } from './dashboard-theme';
import TelemetryV3Panel from './telemetry-v3/TelemetryV3Panel';
import { detectLaunchT } from '@/lib/telemetry/launchDetect';
import Timeline, { fmtClock } from './Timeline';
import DashboardHeader from './DashboardHeader';
import { useDashboardControls } from './dashboard-controls';
import FleetOverview, { balloonColor, balloonTransitionName } from './FleetOverview';
import { positionAtTime, rowAtTime, fleetActivity, previewFleet } from '@/lib/telemetry/fleetPlayback';
import { historyRange } from '@/lib/telemetry/timelineHistory';
import MapLegend from './MapLegend';
import { useGlobePortal, notifyGlobeParent } from './globe-portal';
import CommunityPanel from './CommunityPanel';
import FleetFilters from './FleetFilters';
import { useCommunity } from './community-account';
import { mergeRegisteredBalloons } from '@/lib/community/types';
import { defaultFleetFilters, filterFleet, isPlannedBalloon } from '@/lib/telemetry/fleetFilters';
import { flightTrack } from '@/lib/telemetry/flightTrack';
import { withLatestTelemetry } from '@/lib/telemetry/fleetSummary';

const V2MissionMap = lazy(() => import('./V2MissionMap'));

interface FlightSummary {
    /** Span from first to last loaded packet, ms. Null when no data. */
    durationMs: number | null;
    /** Great-circle distance summed across GPS fixes, km. */
    distanceKm: number;
}

const positionTracks = new WeakMap<TelemetryRow[], TelemetryRow[]>();
function mappedPosition(rows: TelemetryRow[], time: number | null) {
    let track = positionTracks.get(rows);
    if (!track) {
        const validTimes = new Set(flightTrack(rows).map(point => point.t));
        track = rows.filter(row => validTimes.has(row.t));
        positionTracks.set(rows, track);
    }
    return positionAtTime(track, time);
}

export default function MissionControlScreen() {
    const globeStage = useGlobePortal();
    const [interfacePainted, setInterfacePainted] = useState(false);
    useEffect(() => {
        // Let the controls paint before importing and initializing the map.
        let frame = requestAnimationFrame(() => {
            frame = requestAnimationFrame(() => setInterfacePainted(true));
        });
        return () => cancelAnimationFrame(frame);
    }, []);
    const searchParams = new URLSearchParams(window.location.search);
    const initialSelectedId = searchParams.get('device');

    const {
        devices: registryDevices, selectedId, setSelectedId, rows, loading: registryLoading, refetch,
    } = useTelemetry({ initialSelectedId });
    const community = useCommunity();
    useEffect(() => { if (community.focusDevice) setSelectedId(community.focusDevice); }, [community.focusDevice, setSelectedId]);
    const fleetHistory = useFleetHistory(registryDevices.filter(device => device.connectionStatus !== 'pending'), selectedId === null);
    const devices = useMemo(() => mergeRegisteredBalloons(registryDevices.map(device =>
        withLatestTelemetry(device, device.id === selectedId ? rows : fleetHistory.rowsByDevice[device.id]),
    ), community.balloons, community.user?.id), [registryDevices, community.balloons, community.user?.id, fleetHistory.rowsByDevice, selectedId, rows]);
    const [filters, setFilters] = useState(defaultFleetFilters);
    useEffect(() => { if (community.revision) refetch(); }, [community.revision, refetch]);
    useEffect(() => { if (!community.account) setFilters(current => ({...current,mine:false})); }, [community.account]);
    const filteredDevices = useMemo(() => filterFleet(devices, filters, community.user?.id ?? null, Date.now()), [devices,filters,community.user?.id]);
    const filteredIds = new Set(filteredDevices.map(device => device.id));

    const [fleetScrubT, setFleetScrubT] = useState<number | null>(null);
    const transitionRef = useRef<ViewTransition | null>(null);
    const [transitionId, setTransitionId] = useState<string | null>(null);
    const [scrubT, setScrubT] = useState<number | null>(null);
    /* True only while the user is actively dragging the scrubber — used to hide
     * the day/night terminator during a drag (it reappears on release). */
    const [isScrubbing, setIsScrubbing] = useState(false);
    /* Null scrub = follow the latest packet so the page behaves "live". */
    const followLive = scrubT === null;

    /* Mobile only: charts live in a pull-up drawer, hidden by default. */
    const [chartsOpen, setChartsOpen] = useState(false);

    /* The whole flight is always in view (no range zoom). */
    const visibleRows = rows;

    const registeredDevice = devices.find(device => device.id === selectedId);
    const lastRecordedT = rows.length ? rows[rows.length - 1].t : null;
    const recordsBeforeLaunch = registeredDevice?.launchedAt != null && lastRecordedT !== null
        && lastRecordedT < registeredDevice.launchedAt;
    /* Earlier stored records belong to replay, even if the registry still says
     * flying. A forecast for that later launch does not describe these rows. */
    const forecast = useForecastPath(recordsBeforeLaunch || registeredDevice?.status === 'planned' ? null : selectedId);
    const archived = ['landed', 'recovered', 'retired', 'lost'].includes(
        registeredDevice?.status?.toLowerCase() ?? '',
    ) || recordsBeforeLaunch;

    function pickTime(time: number | null) {
        if (time === null || !archived || rows.length === 0) {
            setScrubT(time);
            return;
        }
        // Archived flights replay recorded packets, including across radio gaps.
        const nearest = rows.reduce((best, row) =>
            Math.abs(row.t - time) < Math.abs(best.t - time) ? row : best,
        );
        setScrubT(nearest.t);
    }

    const isMobile = useIsMobile();
    const { theme } = useDashboardTheme();
    useEffect(() => { notifyGlobeParent('theme', { theme }); }, [theme]);
    useEffect(() => {
        if (globeStage === 'dashboard') {
            setSelectedId(new URLSearchParams(window.parent.location.search).get('device'));
            return;
        }
        if (globeStage !== 'footer') return;
        setSelectedId(null);
        setScrubT(null);
        setFleetScrubT(null);
        setChartsOpen(false);
    }, [globeStage, setSelectedId]);

    /* scrubT may sit in the future (along the forecast); only clamp it back if
     * it falls before the first packet (e.g. on a stale carry-over). */
    useEffect(() => {
        if (visibleRows.length === 0 || followLive) return;
        const t0 = visibleRows[0].t;
        if (scrubT! < t0) setScrubT(t0);
    }, [visibleRows, scrubT, followLive]);

    /* "Now" boundary = the latest packet (observed↔forecast divide). */
    const packetEndT = visibleRows.length ? visibleRows[visibleRows.length - 1].t : null;
    /* When GPS is stale, "now" is the dead-reckoned forecast origin — well past the
     * last packet — so live should show the balloon's ESTIMATED current position
     * there, not the last fix. When GPS is fresh the last packet IS now, so we leave
     * the live cursor exactly where it was (no behavior change for live balloons). */
    const liveOriginT = !archived && forecast.staleGps ? forecast.originT : null;
    const effectiveScrubT: number | null = followLive ? (liveOriginT ?? packetEndT) : scrubT;
    /* In the future leg the charts hold the last real reading. */
    const isFuture = effectiveScrubT !== null && packetEndT !== null && effectiveScrubT > packetEndT;

    const scrubRow: TelemetryRow | null = useMemo(() => {
        if (!visibleRows.length || effectiveScrubT === null) return null;
        return rowAtTime(visibleRows, effectiveScrubT) ?? visibleRows[0];
    }, [visibleRows, effectiveScrubT]);

    /* Median packet cadence — used to tell "fresh reading" from a gap. */
    const medianDt = useMemo(() => {
        if (visibleRows.length < 2) return 0;
        const dts: number[] = [];
        for (let i = 1; i < visibleRows.length; i++) dts.push(visibleRows[i].t - visibleRows[i - 1].t);
        dts.sort((a, b) => a - b);
        return dts[Math.floor(dts.length / 2)] || 0;
    }, [visibleRows]);

    /* No live reading at the cursor: out in the forecast, OR sitting in a
     * transmission gap (the shown packet is much older than the cursor). The
     * sidebar blanks its point-in-time values in either case. */
    const scrubInGap = effectiveScrubT !== null && scrubRow !== null && medianDt > 0
        && effectiveScrubT - scrubRow.t > medianDt * 3;
    const noReading = isFuture || scrubInGap;

    /* The device list is loaded only on page-load now, so its per-device last-contact /
     * latest-fix go stale. Keep the SELECTED device's live by re-sourcing them from the
     * incremental telemetry `rows` (polled every 60 s). */
    const selectedDevice: DeviceSummary | null = useMemo(() => {
        const base = selectedId ? devices.find(d => d.id === selectedId) ?? null : null;
        if (!base || rows.length === 0) return base;
        const fixRow = [...rows].reverse().find(r => r.lat != null && r.lon != null);
        return {
            ...base,
            lastContactT: rows[rows.length - 1].t,
            latestFix: fixRow
                ? { lat: fixRow.lat as number, lon: fixRow.lon as number, alt: fixRow.alt, t: fixRow.t }
                : base.latestFix,
        };
    }, [selectedId, devices, rows]);

    /* Ticking wall-clock for "time to present". null on server + first client
     * render (SSR-safe), then live; refreshed each minute. */
    const [nowMs, setNowMs] = useState<number | null>(null);
    useEffect(() => {
        setNowMs(Date.now());
        const id = setInterval(() => setNowMs(Date.now()), 60_000);
        return () => clearInterval(id);
    }, []);

    /* Launch moment derived from the telemetry itself (first decisive climb),
     * NOT devices.launched_at — a payload can soak on the bench for days
     * before release, and the flight clock must not count that. Null while
     * still on the ground. The stamped launched_at is passed as a fallback
     * for windows that begin already airborne (archive replays, or a live
     * flight first heard after a radio blackout — the first heard packet is
     * only a lower bound on how long it's been up). */
    const launchT = useMemo(
        () => detectLaunchT(rows, selectedDevice?.launchedAt ?? null),
        [rows, selectedDevice?.launchedAt],
    );

    /* Whole-flight totals (independent of the timeline range zoom).
     * Duration runs from the detected launch to the present (not the last
     * ping), so it keeps counting while the balloon is aloft — and stays '-'
     * until the balloon actually climbs. Distance is the length of the
     * hindcast line — the wind-reconstructed path through GPS gaps — which is
     * more realistic than straight-line hops between sparse fixes. Falls back
     * to the GPS-fix sum if no hindcast. */
    const flightSummary: FlightSummary = useMemo(() => {
        if (rows.length === 0 || launchT === null) return { durationMs: null, distanceKm: 0 };
        /* Until the clock mounts, fall back to the last packet (deterministic). */
        const endT = archived ? rows[rows.length - 1].t : (nowMs ?? rows[rows.length - 1].t);
        const durationMs = Math.max(0, endT - launchT);
        let distanceKm = 0;
        const hindcast = forecast.hindcastPath;
        if (hindcast && hindcast.length >= 2) {
            for (let i = 1; i < hindcast.length; i++) {
                distanceKm += haversineKm(hindcast[i - 1][1], hindcast[i - 1][0], hindcast[i][1], hindcast[i][0]);
            }
        } else {
            const fixes = rows.filter(r => r.t >= launchT && r.lat !== null && r.lon !== null) as Array<TelemetryRow & { lat: number; lon: number }>;
            for (let i = 1; i < fixes.length; i++) {
                distanceKm += haversineKm(fixes[i - 1].lat, fixes[i - 1].lon, fixes[i].lat, fixes[i].lon);
            }
        }
        return { durationMs, distanceKm };
    }, [rows, forecast.hindcastPath, nowMs, launchT, archived]);

    /* What the panel header shows as "Launched …": the telemetry-detected
     * moment, not the hand-set devices row. Pre-launch this is null and the
     * panel reads "Awaiting launch". */
    const displayDevice: DeviceSummary | null = useMemo(
        () => (selectedDevice ? { ...selectedDevice, launchedAt: launchT } : null),
        [selectedDevice, launchT],
    );

    const isFleet = selectedId === null;
    const fleetHistories = useMemo(() => Object.values(fleetHistory.rowsByDevice), [fleetHistory.rowsByDevice]);
    const fleetLastT = useMemo(() => historyRange(fleetHistories)?.end ?? null, [fleetHistories]);
    const fleetRecorded = fleetLastT !== null && Date.now() - fleetLastT > 15 * 60_000;
    const fleetBalloons = useMemo<V2Balloon[]>(() => devices.flatMap(device => {
        const position = mappedPosition(fleetHistory.rowsByDevice[device.id] ?? [], fleetScrubT);
        return position ? [{ id: device.id, ...position }] : [];
    }), [devices, fleetHistory.rowsByDevice, fleetScrubT]);
    const fleetFitBalloons = useMemo<V2Balloon[]>(() => devices.flatMap(device => {
        const position = mappedPosition(fleetHistory.rowsByDevice[device.id] ?? [], null);
        return position ? [{ id: device.id, ...position }] : [];
    }), [devices, fleetHistory.rowsByDevice]);
    const previewIds = new Set(previewFleet(devices, fleetHistory.rowsByDevice, Date.now()).map(device => device.id));
    const portalPreview = globeStage === 'footer' || globeStage === 'entering';
    const shownFleet = portalPreview ? fleetBalloons.filter(balloon => previewIds.has(balloon.id)) : fleetBalloons.filter(balloon => filteredIds.has(balloon.id));
    const plannedCount = filteredDevices.filter(device => isPlannedBalloon(device.status)).length;
    const activity = fleetActivity(filteredDevices.filter(device => !isPlannedBalloon(device.status)), fleetHistory.rowsByDevice, Date.now());
    const flightCaption = activity.active > 0
        ? `${activity.active} active ${activity.active === 1 ? 'balloon' : 'balloons'}`
        : `${activity.inactive} inactive ${activity.inactive === 1 ? 'balloon' : 'balloons'}`;
    const fleetCaption = plannedCount ? `${activity.active + activity.inactive ? `${flightCaption} / ` : ''}${plannedCount} planned ${plannedCount === 1 ? 'balloon' : 'balloons'}` : flightCaption;

    const transitionPanel = useCallback((id: string | null, update: () => void, animate = true) => {
        transitionRef.current?.skipTransition();
        if (!animate || !document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            update();
            return;
        }
        // Capture the selected card separately; the other cards share one list snapshot.
        flushSync(() => setTransitionId(id));
        transitionRef.current = document.startViewTransition(() => flushSync(update));
        void transitionRef.current.ready.catch(() => {}); // Interrupted transitions still apply the selection.
    }, []);

    const handleSelectDevice = useCallback((id: string, animate = true) => {
        transitionPanel(id, () => {
            setSelectedId(id);
            setScrubT(null);
            setChartsOpen(false);
            window.history.replaceState(window.history.state, '', `/dashboard?device=${encodeURIComponent(id)}`);
            notifyGlobeParent('route', { path: `/dashboard?device=${encodeURIComponent(id)}` });
        }, animate);
    }, [setSelectedId, transitionPanel]);

    function showFleet(animate = true) {
        transitionPanel(selectedId, () => {
            setSelectedId(null);
            setScrubT(null);
            setChartsOpen(false);
            window.history.replaceState(window.history.state, '', '/dashboard');
            notifyGlobeParent('route', { path: '/dashboard' });
        }, animate);
    }

    const panelProps = {
        device: displayDevice, devices, onSelect: handleSelectDevice, scrubRow,
        summary: flightSummary, rows, isFuture: noReading, recordedHistory: archived, onPickTime: pickTime,
    };

    return (
        <div className="sl-app fleet-app" data-theme={theme}>
            <main className="fleet-layout" data-detail={!isFleet} data-loading={registryLoading}>
                <aside className="tlm-panel dashboard-panel fleet-panel">
                    <DashboardHeader onBack={isFleet ? undefined : showFleet} />
                    <CommunityPanel />
                    {isFleet ? (
                        <><FleetFilters value={filters} onChange={setFilters} signedIn={Boolean(community.account)} count={filteredDevices.length} />
                        <FleetOverview devices={filteredDevices} {...fleetHistory} loading={registryLoading || fleetHistory.loading} scrubT={fleetScrubT} now={nowMs ?? Date.now()} onSelect={handleSelectDevice} transitionId={transitionId} /></>
                    ) : (
                        <div className="dashboard-detail-content tlm-scroll" style={{ viewTransitionName: balloonTransitionName(selectedId) }}>
                            <TelemetryV3Panel {...panelProps} variant={isMobile ? 'summary' : 'full'} />
                        </div>
                    )}
                    <footer className="dashboard-footer">
                        <nav aria-label="Stratolink"><a href="/docs" target="_top">docs</a><a href="/blog" target="_top">blog</a><a href="mailto:contact@stratolink.org">contact</a></nav>
                        <span>© stratolink 2026</span>
                    </footer>
                </aside>
                <div className="dashboard-map fleet-map">
                    {interfacePainted && !registryLoading && <MapColumn
                        isFleet={isFleet}
                        fleetBalloons={shownFleet}
                        fleetFitBalloons={portalPreview ? fleetFitBalloons : fleetFitBalloons.filter(balloon => filteredIds.has(balloon.id))}
                        fleetDevices={portalPreview ? devices : filteredDevices}
                        fleetHistory={fleetHistory.rowsByDevice}
                        fleetReady={!registryLoading && !fleetHistory.loading}
                        fleetCaption={fleetCaption}
                        onSelectBalloon={handleSelectDevice}
                        visibleRows={visibleRows}
                        scrubRow={scrubRow}
                        selectedDevice={selectedDevice}
                        forecast={forecast}
                        scrubT={isFleet ? fleetScrubT : effectiveScrubT}
                        terminatorDate={isFleet ? fleetScrubT ?? (fleetRecorded ? fleetLastT : null) : archived ? effectiveScrubT : scrubT}
                        scrubbing={isScrubbing}
                        isFuture={isFuture}
                        noReading={noReading}
                        colorScheme={theme}
                        onPickTime={pickTime}
                    />}
                    <div className="fleet-timeline">
                        <Timeline
                            histories={isFleet ? fleetHistories : [visibleRows]}
                            scrubT={isFleet ? fleetScrubT : scrubT}
                            onScrub={isFleet ? setFleetScrubT : pickTime}
                            archived={isFleet ? fleetRecorded : archived}
                            onScrubbingChange={setIsScrubbing}
                            futureEndT={isFleet ? null : forecast.endT}
                            originT={isFleet ? null : liveOriginT}
                            floating
                        />
                    </div>
                </div>
                {isMobile && !isFleet && <>
                    <div style={{ height: DRAWER_HANDLE_H, flexShrink: 0 }} />
                    <ChartsDrawer open={chartsOpen} onToggle={() => setChartsOpen(value => !value)}>
                        <div className="tlm-panel tlm-scroll" style={{ minHeight: 0, overflowY: 'auto' }}>
                            <TelemetryV3Panel {...panelProps} variant="charts" />
                        </div>
                    </ChartsDrawer>
                </>}
            </main>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Left column — brand/connection strip, balloon switcher, charts.
 * ────────────────────────────────────────────────────────────── */

function BrandStrip() {
    return (
        <div style={{
            display: 'flex', alignItems: 'center',
            padding: '9px 18px', flexShrink: 0,
            borderBottom: '1px solid var(--sl-border)', background: 'var(--sl-bg-1)',
        }}>
            <a href="/" style={{
                display: 'flex', alignItems: 'center', gap: 9,
                fontFamily: 'var(--sl-mono)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--sl-text-hi)', textDecoration: 'none', cursor: 'pointer',
            }}>
                <span aria-hidden style={{ color: 'var(--sl-ok)', display: 'inline-flex' }}>
                    <svg width={18} height={18} viewBox="0 0 32 32" fill="none">
                        <rect x={14} y={4} width={4} height={4} fill="currentColor" />
                        <rect x={12} y={14} width={8} height={2} fill="currentColor" />
                        <rect x={9} y={19} width={14} height={2} fill="currentColor" />
                        <rect x={6} y={24} width={20} height={2} fill="currentColor" />
                    </svg>
                </span>
                STRATOLINK
            </a>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Charts drawer (mobile) — slides up from the bottom over the map.
 * Collapsed, only the grab handle peeks above the bottom edge.
 * ────────────────────────────────────────────────────────────── */
const DRAWER_HANDLE_H = 46;

function ChartsDrawer({ open, onToggle, children }: {
    open: boolean;
    onToggle: () => void;
    children: React.ReactNode;
}) {
    return (
        <div
            className="charts-drawer"
            style={{
                position: 'absolute', left: 0, right: 0, bottom: 0,
                maxHeight: 'min(78dvh, 100%)', zIndex: 30,
                display: 'flex', flexDirection: 'column',
                background: 'var(--sl-bg-1)',
                borderTop: '1px solid var(--sl-border)',
                borderRadius: '22px 22px 0 0', overflow: 'hidden',
                boxShadow: '0 -2px 12px rgba(26, 28, 27, 0.08)',
                transform: open ? 'translateY(0)' : `translateY(calc(100% - ${DRAWER_HANDLE_H}px))`,
                transition: 'transform 0.32s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
        >
            <button
                type="button"
                onClick={onToggle}
                aria-expanded={open}
                style={{
                    flexShrink: 0, height: DRAWER_HANDLE_H,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4,
                    background: 'transparent', border: 'none', cursor: 'pointer', width: '100%',
                    padding: 0,
                }}
            >
                <span style={{
                    fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase',
                    color: 'var(--sl-text-dim2)', fontFamily: 'var(--sl-sans)',
                }}>
                    {open ? 'Hide charts' : 'View charts'}
                    <FontAwesomeIcon icon={open ? faChevronDown : faChevronUp} style={{ marginLeft: 8 }} />
                </span>
            </button>
            <div inert={!open} aria-hidden={!open} style={{ minHeight: 0, overflowY: 'auto', paddingBottom: 'max(10px, env(safe-area-inset-bottom))' }}>
                {children}
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Balloon card — monitored device + switcher + scrub-time vitals.
 * ────────────────────────────────────────────────────────────── */
function BalloonCard({ device, devices, onSelect, scrubRow, summary }: {
    device: DeviceSummary | null;
    devices: DeviceSummary[];
    onSelect: (id: string) => void;
    scrubRow: TelemetryRow | null;
    summary: FlightSummary;
}) {
    const hasFix = scrubRow?.lat !== null && scrubRow?.lat !== undefined;
    return (
        <div style={{
            flexShrink: 0,
            padding: '16px 18px',
            borderBottom: '1px solid var(--sl-border)',
            background: 'var(--sl-bg-1)',
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                    <div className="sl-label-xs">MONITORING</div>
                    <select
                        value={device?.id ?? ''}
                        onChange={(e) => onSelect(e.target.value)}
                        style={{
                            marginTop: 1,
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--sl-text-hi)',
                            fontFamily: 'var(--sl-mono)',
                            fontSize: 21,
                            fontWeight: 600,
                            letterSpacing: '-0.02em',
                            cursor: 'pointer',
                            padding: 0,
                            outline: 'none',
                            maxWidth: 250,
                        }}
                    >
                        {devices.length === 0 && <option value="">no devices</option>}
                        {devices.map(d => (
                            <option key={d.id} value={d.id} style={{ background: 'var(--sl-bg-2)' }}>
                                {d.callsign ?? d.id}
                            </option>
                        ))}
                    </select>
                    {device?.callsign && (
                        <div className="sl-label-sm" style={{ marginTop: 2 }}>{device.id}</div>
                    )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    <span className={'sl-pill ' + (hasFix ? 'teal' : 'amber')}>
                        {hasFix ? 'FIX VALID' : 'NO FIX'}
                    </span>
                    <span className="sl-pill dim">{device?.status ? device.status.toUpperCase() : '-'}</span>
                </div>
            </div>

            <div className="sl-label-sm" style={{ marginBottom: 12 }}>
                {device?.launchedAt ? `launched ${fmt.datetime(device.launchedAt)}` : 'not launched'}
            </div>

            <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '4px 14px',
            }}>
                <Vital label="ALT (PRES)" accent
                    value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                <Vital label="TOTAL TIME" accent
                    value={summary.durationMs != null ? fmt.duration(summary.durationMs) : '-'} />
                <Vital label="TOTAL DIST" accent
                    value={`${Math.round(summary.distanceKm)} km`} />
            </div>
        </div>
    );
}

function Vital({ label, value, accent }: {
    label: string;
    value: React.ReactNode;
    accent?: boolean;
}) {
    return (
        <div>
            <div className="sl-label-xs">{label}</div>
            <div style={{
                fontSize: 18,
                marginTop: 4,
                fontVariantNumeric: 'tabular-nums',
                fontFamily: 'var(--sl-mono)',
                fontWeight: 500,
                letterSpacing: '-0.02em',
                color: accent ? 'var(--sl-ok)' : 'var(--sl-text-hi)',
            }}>
                {value}
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Chart stack — synchronized to the scrub time.
 * ────────────────────────────────────────────────────────────── */
function ChartStack({ visibleRows, rows, scrubT, scrubRow }: {
    visibleRows: TelemetryRow[];
    rows: TelemetryRow[];
    scrubT: number | null;
    scrubRow: TelemetryRow | null;
}) {
    const tStart = visibleRows.length ? visibleRows[0].t : null;
    const tEnd   = visibleRows.length ? visibleRows[visibleRows.length - 1].t : null;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, flex: 1 }}>
            <div style={{ flex: 1, padding: '4px 14px 8px', overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                {visibleRows.length < 2 ? (
                    <div style={{
                        height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: 'var(--sl-text-dim2)', fontSize: 12, letterSpacing: '0.10em', textTransform: 'uppercase',
                    }}>
                        Awaiting telemetry packets
                    </div>
                ) : (
                    <>
                        <ChartRow title="ALT (GPS)" unit="m" color="var(--sl-c-alt)" rows={visibleRows} getY={r => r.alt} scrubT={scrubT}
                            value={scrubRow?.alt != null ? `${scrubRow.alt.toFixed(0)} m` : '-'} />
                        <ChartRow title="ALT (PRES)" unit="m" color="var(--sl-c-alt)" rows={visibleRows} getY={r => r.presAlt} scrubT={scrubT}
                            value={fmtAltitudeM(scrubRow?.presAlt ?? null)} />
                        <ChartRow title="BATTERY" unit="V" color="var(--sl-c-batt)" rows={visibleRows} getY={r => r.batt} scrubT={scrubT}
                            value={scrubRow?.batt != null ? `${scrubRow.batt.toFixed(2)} V` : '-'} min={3.0} max={5.5} />
                        <ChartRow title="SOLAR" unit="V" color="var(--sl-c-solar)" rows={visibleRows} getY={r => r.sol} scrubT={scrubT}
                            value={scrubRow?.sol != null ? `${scrubRow.sol.toFixed(2)} V` : '-'} min={0} max={6} />
                        <ChartRow title="TEMPERATURE" unit="°C" color="var(--sl-c-temp)" rows={visibleRows} getY={r => r.temp} scrubT={scrubT}
                            value={scrubRow?.temp != null ? `${scrubRow.temp.toFixed(1)} °C` : '-'} />
                        <ChartRow title="PRESSURE" unit="hPa" color="var(--sl-c-pres)" rows={visibleRows} getY={r => r.pres} scrubT={scrubT}
                            value={fmtPressure(scrubRow?.pres ?? null)} />
                        <ChartRow title="RSSI" unit="dBm" color="var(--sl-c-rf)" rows={visibleRows} getY={r => r.rssi} scrubT={scrubT}
                            value={scrubRow?.rssi != null ? `${scrubRow.rssi.toFixed(0)} dBm` : '-'} />
                        <ChartRow title="SNR" unit="dB" color="var(--sl-c-rf)" rows={visibleRows} getY={r => r.snr} scrubT={scrubT}
                            value={scrubRow?.snr != null ? `${scrubRow.snr.toFixed(1)} dB` : '-'} />
                        <ChartRow title="GPS SATELLITES" unit="" color="var(--sl-c-sats)" rows={visibleRows} getY={r => r.sats} scrubT={scrubT}
                            value={scrubRow?.sats != null ? `${scrubRow.sats}` : '-'} min={0} max={28} />
                    </>
                )}
            </div>

            {tStart !== null && tEnd !== null && (
                <div style={{
                    padding: '7px 16px 9px 40px', borderTop: '1px solid var(--sl-border)', flexShrink: 0,
                    fontSize: 10, color: 'var(--sl-text-dim2)',
                    fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                }}>
                    <span>{fmtClock(tStart)}</span>
                    <span style={{ fontFamily: 'var(--sl-sans)', letterSpacing: '0.1em', textTransform: 'uppercase', fontSize: 9, color: 'var(--sl-text-dim3)' }}>
                        {visibleRows.length} fixes over time <FontAwesomeIcon icon={faArrowRight} />
                    </span>
                    <span>{fmtClock(tEnd)}</span>
                </div>
            )}
        </div>
    );
}

function ChartRow({ title, unit, color, rows, getY, scrubT, value, min, max }: {
    title: string;
    unit: string;
    color: string;
    rows: TelemetryRow[];
    getY: (r: TelemetryRow) => number | null;
    scrubT: number | null;
    value: string;
    min?: number;
    max?: number;
}) {
    /* Measure both dimensions so each chart grows to fill its share of the
     * column height — the rows flex to fill, no gap left at the bottom. */
    const { ref, width, height } = useElementSize(360, 48);
    return (
        <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) 92px',
            alignItems: 'stretch',
            padding: '4px 0',
            borderBottom: '1px solid var(--sl-border)',
            minWidth: 0,
            flex: '1 1 0',
            minHeight: 56,
        }}>
            <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                <div className="sl-label-xs" style={{ color: 'var(--sl-text-hi)', fontSize: 9, marginBottom: 2, flexShrink: 0 }}>
                    {title}{unit && <span style={{ color: 'var(--sl-text-dim3)', marginLeft: 4 }}>{unit}</span>}
                </div>
                <div ref={ref} style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
                    <Chart
                        data={rows}
                        getY={getY}
                        width={width}
                        height={height}
                        color={color}
                        padL={40}
                        padR={6}
                        padT={8}
                        padB={8}
                        yTicks={1}
                        strokeWidth={1}
                        hideXAxis
                        tufte
                        scrubT={scrubT ?? undefined}
                        min={min}
                        max={max}
                    />
                </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-end', paddingRight: 4 }}>
                <div style={{ fontSize: 14, color: 'var(--sl-text-hi)', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--sl-mono)', fontWeight: 500 }}>
                    {value}
                </div>
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────
 * Map column — coverage + 3-state flight path + forecast.
 * ────────────────────────────────────────────────────────────── */
function MapColumn({
    isFleet, fleetBalloons, fleetFitBalloons, fleetDevices, fleetHistory, fleetReady, fleetCaption, onSelectBalloon,
    visibleRows,
    scrubRow,
    selectedDevice,
    forecast,
    scrubT,
    terminatorDate,
    scrubbing,
    isFuture,
    noReading,
    colorScheme,
    onPickTime,
}: {
    isFleet: boolean;
    fleetBalloons: V2Balloon[];
    fleetFitBalloons: V2Balloon[];
    fleetDevices: DeviceSummary[];
    fleetHistory: Record<string, TelemetryRow[]>;
    fleetReady: boolean;
    fleetCaption: string;
    onSelectBalloon: (id: string) => void;
    visibleRows: TelemetryRow[];
    scrubRow: TelemetryRow | null;
    selectedDevice: DeviceSummary | null;
    forecast: UseForecastPathResult;
    scrubT: number | null;
    /* True while the scrubber is being dragged — hides the day/night terminator. */
    scrubbing: boolean;
    /** Raw scrub cursor for the day/night terminator: the instant being viewed,
     *  or null when following live (terminator then tracks the real current time).
     *  Distinct from `scrubT` (= effectiveScrubT), which resolves live to the last
     *  packet time and so can't tell "live" from "scrubbed to the latest fix". */
    terminatorDate: number | null;
    isFuture: boolean;
    /** No live reading at the cursor — out in the forecast OR sitting in a
     *  transmission gap. The balloon isn't connected, so its links to the last
     *  gateway shouldn't be drawn. */
    noReading: boolean;
    colorScheme: 'light' | 'dark';
    onPickTime: (t: number) => void;
}) {
    /* On mobile the timeline floats over the map's bottom edge; bias the camera
     * up so the globe/track reads as centered in the visible area. */
    const isMobile = useIsMobile();
    const globeStage = useGlobePortal();
    const portalPreview = globeStage === 'footer' || globeStage === 'entering';
    const { showGateways, showReceivingStations, showDayNight, showFlightTrail, showProjectedPath } = useDashboardControls(!isFleet);
    const trackPoints: V2FlightPoint[] = useMemo(() => flightTrack(visibleRows), [visibleRows]);

    /* The likely (reconstructed) path used to glide the balloon as you scrub.
     * Prefer the backend's per-point timestamps, which are anchored to the
     * actual GPS-fix times — so the marker stays in lockstep with the transmit
     * dots. (The old even-by-index spacing drifted: dense early segments got
     * stretched in time, pushing dots ahead of the marker.) Fall back to even
     * spacing only for forecasts computed before the timed track existed. */
    const hindcastTrack: V2FlightPoint[] = useMemo(() => {
        const timed = forecast.hindcastTrack;
        if (timed.length >= 2) return timed.map(p => ({ lon: p.lon, lat: p.lat, t: p.t }));
        const pts = forecast.hindcastPath;
        if (pts.length < 2 || trackPoints.length === 0) return [];
        const t0 = trackPoints[0].t;
        const t1 = trackPoints[trackPoints.length - 1].t;
        const span = t1 - t0 || 1;
        return pts.map(([lon, lat], i) => ({ lon, lat, t: t0 + (i / (pts.length - 1)) * span }));
    }, [forecast.hindcastTrack, forecast.hindcastPath, trackPoints]);

    /* Split the hindcast into runs by certainty: a segment that bridges a long
     * gap since the last transmission (> LONG_GAP_HR) is "estimated" and drawn
     * tightly-dashed; the rest stay solid. Uses the real per-point timestamps
     * and the actual GPS-fix times — needs the timed track, so older forecasts
     * (no timestamps) just render as one solid line. */
    const hindcastSegments = useMemo<Array<{ coords: Array<[number, number]>; estimated: boolean }>>(() => {
        const track = forecast.hindcastTrack;
        if (track.length < 2) return [];
        const fixT = trackPoints.map(p => p.t).filter(t => Number.isFinite(t)).sort((a, b) => a - b);
        if (fixT.length < 2) return [];
        const LONG_GAP_MS = 6 * 3_600_000;   /* mirrors reconstruction CFG.LONG_GAP_HR */
        /* Is the time `t` inside a fix-to-fix interval longer than the long-gap
         * threshold? (linear scan; the track is short). */
        const estimatedAt = (t: number): boolean => {
            let i = 0;
            while (i < fixT.length - 1 && fixT[i + 1] < t) i++;
            const a = fixT[i];
            const b = fixT[Math.min(i + 1, fixT.length - 1)];
            return b - a >= LONG_GAP_MS;
        };
        const segs: Array<{ coords: Array<[number, number]>; estimated: boolean }> = [];
        let run: Array<[number, number]> = [[track[0].lon, track[0].lat]];
        let runEst: boolean | null = null;
        for (let k = 1; k < track.length; k++) {
            const est = estimatedAt((track[k - 1].t + track[k].t) / 2);
            if (runEst === null) runEst = est;
            if (est !== runEst) {
                segs.push({ coords: run, estimated: runEst });
                /* New run starts at the shared boundary vertex so the lines join. */
                run = [[track[k - 1].lon, track[k - 1].lat]];
                runEst = est;
            }
            run.push([track[k].lon, track[k].lat]);
        }
        if (runEst !== null) segs.push({ coords: run, estimated: runEst });
        return segs;
    }, [forecast.hindcastTrack, trackPoints]);

    /* One continuous timed track the balloon glides along, end to end:
     *   hindcast (reconstructed between fixes) → predicted-hindcast (last fix →
     *   "now", the dead-reckon drift) → forecast (now → horizon).
     * So scrubbing moves the balloon along the WHOLE drawn line, not just the
     * forecast leg — no jump at the last fix. */
    const fullTrack: V2FlightPoint[] = useMemo(() => {
        const out: V2FlightPoint[] = [...(hindcastTrack.length >= 2 ? hindcastTrack : trackPoints)];
        const lastT = out.length ? out[out.length - 1].t : null;
        const originT = forecast.originT;

        /* predicted-hindcast: last fix → now (only present when GPS is stale) */
        const ph = forecast.predictedHindcast;
        if (ph.length >= 2 && lastT !== null && originT !== null && originT > lastT) {
            const span = originT - lastT;
            for (let i = 1; i < ph.length; i++) {
                out.push({ lon: ph[i][0], lat: ph[i][1], t: lastT + (i / (ph.length - 1)) * span });
            }
        }

        /* forecast: origin ("now") → horizon end */
        const fp = forecast.path;
        const startT = originT ?? lastT;
        const endT = forecast.endT;
        if (fp.length >= 2 && startT !== null && endT !== null && endT > startT) {
            const span = endT - startT;
            for (let i = 1; i < fp.length; i++) {
                out.push({ lon: fp[i][0], lat: fp[i][1], t: startT + (i / (fp.length - 1)) * span });
            }
        }
        return out;
    }, [hindcastTrack, trackPoints, forecast.predictedHindcast, forecast.path, forecast.originT, forecast.endT]);

    /* Balloon position: interpolate along the full track at the cursor time.
     * Altitude is real telemetry only in the observed past; null once we're past
     * the last packet (predicted-hindcast / forecast legs have no readings). */
    const balloon: V2Balloon | null = useMemo(() => {
        if (!selectedDevice) return null;
        const pos = scrubT !== null && fullTrack.length >= 2
            ? lerpAlongTrack(fullTrack, scrubT)
            : (fullTrack.length ? [fullTrack[fullTrack.length - 1].lon, fullTrack[fullTrack.length - 1].lat] as [number, number] : null);
        if (!pos) return null;
        /* The forecast/predicted track keeps longitudes unwrapped past ±180 (so
         * its line stays continuous across the antimeridian); the balloon marker
         * is a single point, so fold its lon back into [-180,180] or it exceeds
         * WGS84 and gets dropped, making the marker vanish past 180°. */
        const lon = ((pos[0] + 180) % 360 + 360) % 360 - 180;
        return { id: selectedDevice.id, lat: pos[1], lon, altitude_m: isFuture ? null : (scrubRow?.alt ?? null) };
    }, [selectedDevice, scrubRow, fullTrack, scrubT, isFuture]);

    /* Gateways + reception links belong to a real transmission. Hide them
     * whenever the balloon isn't connected at the cursor — out in the forecast
     * OR inside a transmission gap — so we don't draw links to the last gateway
     * during a "No Connection" stretch. */
    const mapGateways: V2Gateway[] = useMemo(() => {
        const list = noReading ? null : (scrubRow?.gateways ?? null);
        if (!list) return [];
        return list
            .filter(g => g.lat !== null && g.lon !== null)
            .map(g => ({ gateway_id: g.gateway_id, lat: g.lat as number, lon: g.lon as number, rssi: g.rssi, snr: g.snr }));
    }, [scrubRow, noReading]);

    /* Whether this flight ever reported a receiver — constant across scrubbing,
     * so the legend stays stable even where no receiver is currently drawn. */
    const flightHasGateways = useMemo(
        () => visibleRows.some(r => (r.gateways?.length ?? 0) > 0),
        [visibleRows],
    );

    /* Connector from the last real fix to the dead-reckoned "now". Prefer the
     * wind-integrated predicted-hindcast curve; fall back to a straight line for
     * forecasts that predate that field. */
    const staleLine = useMemo<Array<[number, number]> | null>(() => {
        if (!forecast.staleGps) return null;
        if (forecast.predictedHindcast.length >= 2) return forecast.predictedHindcast;
        if (forecast.path.length === 0 || trackPoints.length === 0) return null;
        const last = trackPoints[trackPoints.length - 1];
        return [[last.lon, last.lat], forecast.path[0]];
    }, [forecast.staleGps, forecast.predictedHindcast, forecast.path, trackPoints]);


    const pickPath: V2FlightPoint[] = trackPoints.length >= 2 ? trackPoints : hindcastTrack;
    const fleetPaths = useMemo(() => fleetDevices.map(device => ({
        deviceId: device.id,
        color: balloonColor(device.id),
        points: flightTrack(fleetHistory[device.id] ?? []),
    })), [fleetDevices, fleetHistory]);

    return (
        <div style={{ flex: 1, position: 'relative', minHeight: 0, minWidth: 0, overflow: 'hidden' }}>
            <Suspense fallback={null}><V2MissionMap
                showGatewayCoverage={!portalPreview && showGateways}
                showReceivingStations={showReceivingStations}
                showDayNight={!portalPreview && showDayNight}
                showFlightPaths={!portalPreview && !isFleet && showFlightTrail}
                showFlightTails={!portalPreview && isFleet && showFlightTrail}
                showProjectedPath={!portalPreview && showProjectedPath}
                fleetForecastIds={isFleet ? fleetDevices.filter(device => {
                    const lastT = fleetHistory[device.id]?.at(-1)?.t;
                    return lastT != null && (device.launchedAt == null || lastT >= device.launchedAt);
                }).map(device => device.id) : []}
                balloons={isFleet ? fleetBalloons : balloon ? [balloon] : []}
                fleetFitBalloons={portalPreview ? fleetFitBalloons.filter(point => fleetBalloons.some(balloon => balloon.id === point.id)) : isFleet ? fleetFitBalloons : undefined}
                fleetPaths={fleetPaths}
                onSelectBalloon={isFleet ? onSelectBalloon : undefined}
                preserveCamera
                activeId={selectedDevice?.id ?? null}
                flightPath={trackPoints}
                autoFit={globeStage === 'standalone' && (isFleet ? fleetReady : visibleRows.length > 0)}
                portalReady={fleetReady}
                playbackT={isFleet ? scrubT : scrubRow?.t ?? null}
                terminatorDate={terminatorDate}
                terminatorScrubbing={scrubbing}
                projection="globe"
                gateways={mapGateways}
                showTransmitPoints
                hindcastPath={forecast.hindcastPath}
                hindcastSegments={hindcastSegments}
                staleLine={staleLine}
                forecastPath={forecast.path}
                forecastEnsemble={forecast.ensemble}
                forecastEllipses={forecast.ellipses}
                divergence={forecast.divergence}
                colorScheme={colorScheme}
                liftPx={globeStage === 'standalone' && isMobile ? 60 : 0}
                wideZoom={isMobile ? 0.8 : 1.5}
                pickPath={pickPath}
                onPickTime={onPickTime}
            /></Suspense>

            <MapLegend
                fleet={isFleet}
                hasForecast={forecast.path.length >= 2 || forecast.ensemble.length > 0 || forecast.ellipses.length > 0 || (staleLine?.length ?? 0) >= 2 || forecast.divergence != null}
                hasHindcast={forecast.hindcastPath.length >= 2 || trackPoints.length >= 2}
                hasEstimated={hindcastSegments.some(s => s.estimated)}
                hasGateways={flightHasGateways}
                colorScheme={colorScheme}
            />

            {isFleet && <div className="map-coordinates fleet-map-caption">{fleetCaption}</div>}
            {!isFleet && balloon && (
                <div className="map-coordinates">
                    <span>
                        {balloon.lat === 37.76 && balloon.lon.toFixed(2) === '-122.44' ? 'San Francisco - approximate' : `${balloon.lat.toFixed(2)}°, ${balloon.lon.toFixed(2)}°`}
                    </span>
                    {/* Very stale: the dead-reckon ran out of wind coverage before
                        "now", so the marker is the last MODELED point, not the real
                        present position. Say so instead of implying a known location. */}
                    {isFuture && forecast.coverageLimited && forecast.originT != null && (
                        <span
                            className="sl-pill amber"
                            title="GPS-dark beyond the predictable horizon - the position shown is the last modeled point; the true current location is unknown."
                        >
                            position uncertain since {new Date(forecast.originT).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}

/* Position [lon, lat] along a time-stamped track at time t, linearly
 * interpolated between the bracketing fixes so the balloon glides. */
function lerpAlongTrack(track: V2FlightPoint[], t: number): [number, number] | null {
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

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}
