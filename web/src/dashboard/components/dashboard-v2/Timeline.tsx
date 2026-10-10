import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowRight, faClock } from '@fortawesome/free-solid-svg-icons';
import { useIsMobile } from '@/hooks/use-mobile';
import { adjacentPacketTime, historyRange, type TimelineHistories } from '@/lib/telemetry/timelineHistory';

/* ──────────────────────────────────────────────────────────────
 * Timeline — full-width scrubber. Drives the charts AND the map.
 * ────────────────────────────────────────────────────────────── */
/* Precise scrubbing (Apple Podcasts style): once dragging the scrubber, moving
 * the pointer AWAY from the track — up or down — trades range for precision.
 * Each band drops the gain so horizontal travel maps to proportionally less
 * time, keeping a 12-day rail finely seekable. Works for mouse and touch.
 * `PRECISE_PULL` = px from the track band where each tier starts;
 * `PRECISE_GAIN[tier]` = time-per-pixel multiplier (tier 0 = 1:1 with the bar). */
const PRECISE_PULL = [30, 60, 90] as const;
const PRECISE_GAIN = [1, 0.5, 0.25, 0.1] as const;
const PRECISE_LABEL = ['', '0.5×', '0.25×', '0.1×'] as const;

export default function Timeline({ histories, scrubT, onScrub, onScrubbingChange, futureEndT, originT = null, floating = false, archived = false }: {
    histories: TimelineHistories;
    scrubT: number | null;
    /* Estimated "now" (dead-reckoned forecast origin); the live cursor parks here
     * instead of the last packet, matching the balloon's estimated position. */
    originT?: number | null;
    /* null re-arms "follow live" — the page tracks each new packet. */
    onScrub: (t: number | null) => void;
    /* Fires true while the user is actively dragging the scrubber, false on
     * release — lets the map hide the day/night terminator during a drag. */
    onScrubbingChange?: (active: boolean) => void;
    /* Forecast horizon end; the bar extends here so the cursor can ride the
     * predicted path into the future. Null = no forecast, bar ends at "now". */
    futureEndT: number | null;
    /* When true, render as a self-contained floating card (overlaid on the
     * map) instead of a full-width bottom row. */
    floating?: boolean;
    archived?: boolean;
}) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    /* Pull-down precise-scrub state: an accumulated scrub time (so reduced-gain
     * drags integrate finger motion rather than snap to absolute X), the last
     * touch X, and the active precision tier (0 = full speed). */
    const scrubAccumRef = useRef<number | null>(null);
    const lastTouchXRef = useRef(0);
    const preciseTierRef = useRef(0);
    const [preciseTier, setPreciseTier] = useState(0);
    /* On mobile the date/time is floated above the thumb instead of taking a
     * column beside the track, so the scrub track spans the full width. */
    const isMobile = useIsMobile();
    /* When there are no rows yet we need a "now" for the empty rail. Reading
     * Date.now() during render is non-deterministic across SSR/hydration (the
     * two clocks differ by a few hundred ms), which mismatches the slider's
     * aria-value* timestamps. So fall back to 0 until mounted, then fill in the
     * real clock client-side. Once telemetry arrives this path is never taken. */
    /* A ticking real-time clock. null on the server + first client render (so
     * hydration matches), then the live time once mounted; refreshed so the
     * "live" marker creeps along the forecast as real time passes. */
    const [clientNow, setClientNow] = useState<number | null>(null);
    useEffect(() => {
        setClientNow(Date.now());
        const id = setInterval(() => setClientNow(Date.now()), 30_000);
        return () => clearInterval(id);
    }, []);
    const nowBase = clientNow ?? 0;
    const range = useMemo(() => historyRange(histories), [histories]);
    const tStart = range?.start ?? nowBase - 24 * 3600 * 1000;
    /* Last real packet — the default load point and the boundary between
     * observed track (red) and forecast (blue). NOT "live". */
    const packetEndT = range?.end ?? nowBase;
    /* "Live" = the actual current time — the balloon's projected position right
     * now. Falls back to the last packet until the clock mounts. */
    const liveT = archived ? packetEndT : (clientNow ?? packetEndT);
    const forecastEndT = !archived && futureEndT !== null && futureEndT > packetEndT ? futureEndT : packetEndT;
    /* Rail spans far enough to include both the forecast horizon and "now". */
    const tEnd = Math.max(forecastEndT, liveT, packetEndT);
    const span = tEnd - tStart || 1;
    const hasFuture = forecastEndT > packetEndT;

    const pct = (t: number) => Math.max(0, Math.min(100, ((t - tStart) / span) * 100));
    const nowFrac = pct(packetEndT);
    const liveFrac = pct(liveT);
    const cursorT = scrubT ?? originT ?? packetEndT;  // live parks at the estimated "now" (else last packet)
    const fraction = pct(cursorT);
    const elapsedW = Math.min(fraction, nowFrac);

    const cursorInFuture = cursorT > packetEndT;
    /* Future leg = the forecast, which is drawn blue on the map. */
    const handleColor = cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-ok)';
    const labelLeft = Math.max(7, Math.min(93, fraction));
    /* Mobile clock width, measured so it can be centered on the thumb yet clamped
     * inside the track (and clear of anything parked at its left, via CSS). */
    const mobileLabelRef = useRef<HTMLDivElement | null>(null);
    const [mobileLabelW, setMobileLabelW] = useState(0);

    /* Offset of the cursor from the real "now" (live): minutes within the hour,
     * hours up to 3 days, then days (e.g. "−10.4d") so a long dead-reckon doesn't
     * read as an unwieldy "−249hr". Within a couple minutes of now it says "live". */
    const relMs = cursorT - liveT;
    const relHr = relMs / 3_600_000;
    const relSign = relHr >= 0 ? '+' : '-';
    const relAbsHr = Math.abs(relHr);
    const relLabel = archived ? 'replay' : Math.abs(relMs) < 120_000
        ? 'live'
        : relAbsHr < 1
            ? `${relSign}${Math.max(1, Math.round(relAbsHr * 60))}m`
            : relAbsHr < 72
                ? `${relSign}${Math.round(relAbsHr)}hr`
                : `${relSign}${(relAbsHr / 24).toFixed(1)}d`;
    const cursorIsLive = !archived && Math.abs(relMs) < 120_000;
    const mobileRelLabel = preciseTier > 0 ? PRECISE_LABEL[preciseTier] : relLabel;
    const mobileLabelText = `${fmtClock(cursorT)} ${mobileRelLabel}`;
    useLayoutEffect(() => {
        const width = mobileLabelRef.current?.offsetWidth ?? 0;
        setMobileLabelW(current => current === width ? current : width);
    }, [mobileLabelText, isMobile]);

    /* Scrubbing (mouse + touch) is incremental — it integrates pointer motion
     * scaled by the active precision gain — rather than snapping to the pointer
     * X. Pointer-down still seeds to the tapped position, so a plain drag at
     * full gain tracks the pointer 1:1, identical to the old absolute behaviour;
     * the precision only engages once the pointer moves away from the track. */
    const setTier = (tier: number) => {
        if (tier !== preciseTierRef.current) { preciseTierRef.current = tier; setPreciseTier(tier); }
    };
    /* Precision tier from how far the pointer is from the track band — in EITHER
     * direction (pull up or down both work). */
    const tierFromY = (clientY: number, rect: DOMRect): number => {
        const dist = clientY > rect.bottom ? clientY - rect.bottom
            : clientY < rect.top ? rect.top - clientY
                : 0;
        return dist < PRECISE_PULL[0] ? 0 : dist < PRECISE_PULL[1] ? 1 : dist < PRECISE_PULL[2] ? 2 : 3;
    };
    const beginDrag = (clientX: number) => {
        onScrubbingChange?.(true);
        const el = trackRef.current;
        if (el) {
            const rect = el.getBoundingClientRect();
            const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            scrubAccumRef.current = tStart + span * f;
            onScrub(scrubAccumRef.current);
        }
        lastTouchXRef.current = clientX;
        setTier(0);
    };
    const moveDrag = (clientX: number, clientY: number) => {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const tier = tierFromY(clientY, rect);
        const dx = clientX - lastTouchXRef.current;
        lastTouchXRef.current = clientX;
        const dt = (dx / rect.width) * span * PRECISE_GAIN[tier];
        const base = scrubAccumRef.current ?? cursorT;
        const next = Math.max(tStart, Math.min(tEnd, base + dt));
        scrubAccumRef.current = next;
        onScrub(next);
        setTier(tier);
    };
    const endDrag = () => {
        onScrubbingChange?.(false);
        setTier(0);
    };

    const onMouseDown = (e: React.MouseEvent) => {
        beginDrag(e.clientX);
        function move(ev: MouseEvent) { moveDrag(ev.clientX, ev.clientY); }
        function up() {
            window.removeEventListener('mousemove', move);
            window.removeEventListener('mouseup', up);
            endDrag();
        }
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
    };
    const onTouchStart = (e: React.TouchEvent) => beginDrag(e.touches[0].clientX);
    const onTouchMove = (e: React.TouchEvent) => moveDrag(e.touches[0].clientX, e.touches[0].clientY);
    const onTouchEnd = () => endDrag();

    const onKeyDown = (event: React.KeyboardEvent) => {
        let next: number;
        if (event.key === 'Home') next = tStart;
        else if (event.key === 'End') next = tEnd;
        /* Arrows step 1% of the rail; Shift+arrows jump packet to packet. */
        else if (event.key === 'ArrowLeft') {
            next = event.shiftKey
                ? adjacentPacketTime(histories, cursorT, 'previous') ?? tStart
                : Math.max(tStart, cursorT - span / 100);
        } else if (event.key === 'ArrowRight') {
            next = event.shiftKey
                ? adjacentPacketTime(histories, cursorT, 'next') ?? tEnd
                : Math.min(tEnd, cursorT + span / 100);
        } else return;
        event.preventDefault();
        onScrub(next);
    };

    /* ── Floating: one slim row — state dot + clock (key info) + the track. ── */
    if (floating) {
        const PAPER = 'var(--sl-chrome-paper)';
        return (
            <div style={{
                position: 'relative',
                display: 'flex', alignItems: 'center', gap: 13,
                height: 32, padding: '0 15px',
                background: 'var(--sl-overlay-bg-blur)',
                backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
                border: '1px solid var(--sl-border)',
                borderRadius: 999,
                boxShadow: '0 1px 5px rgba(26, 28, 27, 0.10)',
                /* No accidental text-selection of the clock while dragging. */
                userSelect: 'none', WebkitUserSelect: 'none',
            }}>
                {/* Precise-scrub speed — a small, quiet multiplier below the bar's
                  * left edge. Anchored to the bar (not the moving thumb/clock),
                  * so it never resizes the track or overflows the screen edge. */}
                {/* Phones show the speed in the clock above the thumb instead: the
                  * space below the bar is under the finger and the charts drawer. */}
                {preciseTier > 0 && !isMobile && (
                    <span style={{
                        position: 'absolute', top: 'calc(100% + 5px)', left: 16,
                        fontFamily: 'var(--sl-mono)', fontSize: 11, fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums', color: 'var(--sl-ok)',
                        whiteSpace: 'nowrap', pointerEvents: 'none',
                        textShadow: '0 1px 3px var(--sl-overlay-bg)',
                    }}>
                        {PRECISE_LABEL[preciseTier]}
                    </span>
                )}
                {/* Desktop: clock sits in a column beside the track. On mobile
                  * it's floated above the thumb (below) so the track gets the
                  * full width for finer control. */}
                {!isMobile && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexShrink: 0 }}>
                        <FontAwesomeIcon icon={faClock} style={{ color: handleColor, fontSize: 10, flexShrink: 0 }} />
                        <span style={{
                            fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 11, fontWeight: 500,
                            color: cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-hi)', whiteSpace: 'nowrap',
                        }}>
                            {fmtClock(cursorT)}
                            {/* Fixed-width slot so the relative label (live / +18hr /
                              * −336hr) can't change the clock column's width and
                              * resize the track as you scrub. Widest is ~"−2160hr"
                              * (full-history start) ≈ 7 monospace chars. */}
                            <span style={{
                                color: cursorIsLive ? 'var(--sl-ok)' : cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-dim2)',
                                marginLeft: 5, display: 'inline-block', minWidth: '7ch', textAlign: 'left',
                            }}>
                                {relLabel}
                            </span>
                        </span>
                    </div>
                )}
                <div
                    ref={trackRef}
                    className="sl-scrub-track"
                    role="slider"
                    aria-label="Flight timeline"
                    aria-valuetext={`${fmtClock(cursorT)} UTC${archived ? ", recorded telemetry" : ""}`}
                    onKeyDown={onKeyDown}
                    tabIndex={0}
                    aria-valuemin={tStart}
                    aria-valuemax={tEnd}
                    aria-valuenow={cursorT}
                    onMouseDown={onMouseDown}
                    onTouchStart={onTouchStart}
                    onTouchMove={onTouchMove}
                    onTouchEnd={onTouchEnd}
                    style={{ position: 'relative', flex: 1, alignSelf: 'stretch', userSelect: 'none', touchAction: 'none' }}
                >
                    {/* Mobile: clock floats above the thumb so it doesn't steal
                      * track width. */}
                    {isMobile && (
                        <div ref={mobileLabelRef} className="sl-scrub-clock" style={{
                            position: 'absolute', bottom: 'calc(100% + 7px)',
                            /* Centered on the thumb, clamped so it can't overflow
                             * the track's right end or slide over the map credit
                             * parked at its left (--timeline-label-min). */
                            left: `clamp(var(--timeline-label-min, 0px), calc(${fraction}% - ${mobileLabelW / 2}px), calc(100% - ${mobileLabelW}px))`,
                            pointerEvents: 'none',
                            fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums',
                            fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
                            color: cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-hi)',
                            textShadow: '0 1px 3px var(--sl-overlay-bg)',
                        }}>
                            {fmtClock(cursorT)}
                            <span style={{ color: preciseTier > 0 || cursorIsLive ? 'var(--sl-ok)' : cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-dim2)', fontWeight: preciseTier > 0 ? 600 : undefined, marginLeft: 5 }}>
                                {mobileRelLabel}
                            </span>
                        </div>
                    )}
                    {/* recessed rail groove — reads as a slider track */}
                    <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: 0, right: 0, height: 4, borderRadius: 2, background: 'var(--sl-bg-2)', border: '1px solid var(--sl-border)' }} />
                    {/* forecast horizon — dashed extension on the rail */}
                    {hasFuture && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 0.5px)', left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 0, borderTop: '1.5px dashed var(--sl-forecast-dashed)' }} />
                    )}
                    {/* elapsed fill */}
                    <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: 0, width: `${elapsedW}%`, height: 4, borderRadius: 2, background: 'var(--sl-ok)' }} />
                    {fraction > nowFrac && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 2px)', left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 4, borderRadius: 2, background: 'var(--sl-forecast)' }} />
                    )}
                    {/* last-transmission notch — boundary between observed track
                      * and forecast. */}
                    {hasFuture && (
                        <div style={{ position: 'absolute', top: 'calc(50% - 3px)', left: `calc(${nowFrac}% - 3px)`, width: 6, height: 6, borderRadius: '50%', background: PAPER, border: '1px solid var(--sl-text-dim2)' }} />
                    )}
                    {/* live marker — the real current time on the rail */}
                    {liveFrac > nowFrac + 0.2 && (
                        <>
                            <div style={{ position: 'absolute', top: 'calc(50% - 8px)', left: `calc(${liveFrac}% - 0.75px)`, width: 1.5, height: 16, background: 'var(--sl-ok)', borderRadius: 1 }} />
                            <div style={{ position: 'absolute', top: 'calc(50% - 11px)', left: `calc(${liveFrac}% - 2px)`, width: 4, height: 4, borderRadius: '50%', background: 'var(--sl-ok)' }} />
                        </>
                    )}
                    {/* draggable thumb — a clear capsule grip */}
                    <div
                        className="sl-scrub-thumb"
                        style={{
                            position: 'absolute', top: 'calc(50% - 9px)', left: `calc(${fraction}% - 4px)`,
                            width: 8, height: 18, borderRadius: 4,
                            background: handleColor, border: `2px solid ${PAPER}`,
                            boxShadow: '0 1px 3px rgba(26, 28, 27, 0.25)',
                        }}
                    />
                </div>
            </div>
        );
    }

    /* ── Inline (mobile): stacked track + start/end stamps. ── */
    return (
        <div style={{
            borderTop: '1px solid var(--sl-border)',
            padding: '8px 20px 9px',
            background: 'var(--sl-bg-1)',
            flexShrink: 0,
        }}>
            <div
                ref={trackRef}
                role="slider"
                aria-label="Flight timeline"
                aria-valuetext={`${fmtClock(cursorT)} UTC${archived ? ', recorded telemetry' : ''}`}
                onKeyDown={onKeyDown}
                tabIndex={0}
                aria-valuemin={tStart}
                aria-valuemax={tEnd}
                aria-valuenow={cursorT}
                onMouseDown={onMouseDown}
                onTouchStart={onTouchStart}
                onTouchMove={onTouchMove}
                onTouchEnd={onTouchEnd}
                style={{ position: 'relative', height: 30, cursor: 'pointer', userSelect: 'none', touchAction: 'none' }}
            >
                <div style={{
                    position: 'absolute', top: -1, left: `${labelLeft}%`, transform: 'translateX(-50%)',
                    fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 10.5, fontWeight: 500,
                    color: cursorIsLive ? 'var(--sl-ok)' : cursorInFuture ? 'var(--sl-forecast)' : 'var(--sl-text-hi)', whiteSpace: 'nowrap', pointerEvents: 'none',
                }}>
                    {fmtClock(cursorT)} - {relLabel}
                </div>
                <div style={{ position: 'absolute', top: 22, left: 0, right: 0, height: 1, background: 'var(--sl-border-hi)' }} />
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 21.5, left: `${nowFrac}%`, width: `${100 - nowFrac}%`, height: 0, borderTop: '1px dashed var(--sl-forecast-dashed)' }} />
                )}
                <div style={{ position: 'absolute', top: 21, left: 0, width: `${elapsedW}%`, height: 2, background: 'var(--sl-ok)' }} />
                {fraction > nowFrac && (
                    <div style={{ position: 'absolute', top: 21, left: `${nowFrac}%`, width: `${fraction - nowFrac}%`, height: 2, background: 'var(--sl-forecast)' }} />
                )}
                <svg width="100%" height="30" style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}>
                    {histories.map((rows, group) => rows.map((r, i) => (
                        <line key={`${group}:${i}`} x1={`${pct(r.t)}%`} y1="25" x2={`${pct(r.t)}%`} y2="28" stroke="var(--sl-text-dim3)" strokeOpacity="0.55" />
                    )))}
                </svg>
                {hasFuture && (
                    <div style={{ position: 'absolute', top: 19.5, left: `calc(${nowFrac}% - 2.5px)`, width: 5, height: 5, borderRadius: '50%', background: 'var(--sl-bg-1)', border: '1px solid var(--sl-text-dim2)' }} />
                )}
                {/* live marker — the real current time on the rail */}
                {liveFrac > nowFrac + 0.2 && (
                    <div style={{ position: 'absolute', top: 16, left: `calc(${liveFrac}% - 0.75px)`, width: 1.5, height: 9, background: 'var(--sl-ok)', borderRadius: 1 }} />
                )}
                <div style={{ position: 'absolute', top: 13, left: `calc(${fraction}% - 0.5px)`, width: 1, height: 16, background: handleColor }} />
                <div style={{ position: 'absolute', top: 18.5, left: `calc(${fraction}% - 3.5px)`, width: 7, height: 7, borderRadius: '50%', background: handleColor, border: '1.5px solid var(--sl-bg-1)' }} />
            </div>
            <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 3,
                fontFamily: 'var(--sl-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 10, color: 'var(--sl-text-dim3)',
            }}>
                <span>{fmtClock(tStart)}</span>
                <span style={{ fontFamily: 'var(--sl-sans)', letterSpacing: '0.14em', textTransform: 'uppercase', fontSize: 8.5, color: 'var(--sl-text-dim2)' }}>
                    drag to replay{hasFuture && <> - <FontAwesomeIcon icon={faArrowRight} /> forecast</>}
                </span>
                <span>{fmtClock(tEnd)}</span>
            </div>
        </div>
    );
}

/* Compact UTC clock without seconds, e.g. "05-29 18:55". */
export function fmtClock(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}
