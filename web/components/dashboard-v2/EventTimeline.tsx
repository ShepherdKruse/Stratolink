'use client';

import { useMemo, useRef, useState, useEffect, type CSSProperties } from 'react';
import type { TelemetryRow } from './atoms';
import { buildFlightNarrative, type FlightEvent } from '@/lib/telemetry/flightNarrative';

type EventTimelineProps = {
    rows: TelemetryRow[];
    scrubT: number | null;
    onScrub: (t: number | null) => void;
    launchedAt?: number | null;
    floating?: boolean;
};

function fmtClock(ms: number): string {
    const d = new Date(ms);
    const p = (n: number) => String(n).padStart(2, '0');
    return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

export default function EventTimeline({ rows, scrubT, onScrub, launchedAt, floating = false }: EventTimelineProps) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    const narrative = useMemo(
        () => buildFlightNarrative(rows, { launchedAt }),
        [rows, launchedAt],
    );

    const [focusIdx, setFocusIdx] = useState<number | null>(null);

    useEffect(() => {
        setFocusIdx(null);
    }, [rows]);

    const events = narrative?.events ?? [];
    const segments = narrative?.segments ?? [];
    const packetEndT = narrative?.packetEndT ?? 0;
    const fractionToTime = narrative?.fractionToTime ?? (() => 0);
    const timeToFraction = narrative?.timeToFraction ?? (() => 0);

    const visibleSegments = useMemo(() => {
        if (!narrative) return [];
        if (focusIdx == null || focusIdx >= events.length - 1) return segments;
        const t0 = events[focusIdx].t;
        const t1 = events[focusIdx + 1].t;
        return segments.filter((s) => s.t1 >= t0 && s.t0 <= t1);
    }, [narrative, segments, events, focusIdx]);

    const visibleEvents = useMemo(() => {
        if (!narrative) return [];
        if (focusIdx == null) return events;
        return events.filter((e, i) => i === focusIdx || i === focusIdx + 1);
    }, [narrative, events, focusIdx]);

    if (!narrative || rows.length < 2) {
        return null;
    }

    const cursorT = scrubT ?? packetEndT;
    const cursorFrac = timeToFraction(cursorT);

    const visibleWidth = visibleSegments.reduce((s, seg) => s + seg.widthFrac, 0) || 1;

    let run = 0;
    const segmentLayout = visibleSegments.map((seg) => {
        const left = (run / visibleWidth) * 100;
        const w = (seg.widthFrac / visibleWidth) * 100;
        run += seg.widthFrac;
        return { seg, left, width: w };
    });

    const eventPositions = visibleEvents.map((ev, i) => {
        if (focusIdx != null && visibleEvents.length === 2) {
            return { ev, left: i === 0 ? 0 : 100 };
        }
        return { ev, left: timeToFraction(ev.t) * 100 };
    });

    function pickFromClientX(clientX: number) {
        const el = trackRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const f = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const globalF = focusIdx != null
            ? (() => {
                  const t0 = events[focusIdx].t;
                  const t1 = events[focusIdx + 1].t;
                  const localT = t0 + f * (t1 - t0);
                  return timeToFraction(localT);
              })()
            : f;
        const t = fractionToTime(globalF);
        if (Math.abs(t - packetEndT) <= 60_000) {
            onScrub(null);
            return;
        }
        onScrub(t);
    }

    function jumpToEvent(ev: FlightEvent, idx: number) {
        onScrub(ev.kind === 'now' ? null : ev.t);
        if (idx < events.length - 1) setFocusIdx(idx);
        else setFocusIdx(null);
    }

    const onMouseDown = (e: React.MouseEvent) => {
        pickFromClientX(e.clientX);
        const move = (ev: MouseEvent) => pickFromClientX(ev.clientX);
        const up = () => {
            window.removeEventListener('mousemove', move);
            window.removeEventListener('mouseup', up);
        };
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
    };

    const shellStyle: CSSProperties = floating
        ? {
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              padding: '8px 14px 10px',
              background: 'var(--sl-overlay-bg-blur)',
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              border: '1px solid var(--sl-border)',
              borderRadius: 10,
              boxShadow: '0 2px 10px rgba(0,0,0,0.12)',
          }
        : {
              borderTop: '1px solid var(--sl-border)',
              padding: '10px 18px 12px',
              background: 'var(--sl-bg-1)',
              flexShrink: 0,
          };

    const focusLabel =
        focusIdx != null && focusIdx < events.length - 1
            ? `${events[focusIdx].label} → ${events[focusIdx + 1].label}`
            : null;

    return (
        <div style={shellStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span
                    className="mono"
                    style={{ fontSize: 10, color: 'var(--sl-text-dim2)', letterSpacing: '0.06em' }}
                >
                    {fmtClock(cursorT)}
                    {focusLabel && (
                        <span style={{ marginLeft: 8, color: 'var(--sl-text-dim3)' }}>· {focusLabel}</span>
                    )}
                </span>
                {focusIdx != null && (
                    <button
                        type="button"
                        onClick={() => setFocusIdx(null)}
                        className="mono"
                        style={{
                            fontSize: 9,
                            padding: '2px 6px',
                            border: '1px solid var(--sl-border)',
                            borderRadius: 3,
                            background: 'var(--sl-bg-2)',
                            color: 'var(--sl-text-dim2)',
                            cursor: 'pointer',
                        }}
                    >
                        Full flight
                    </button>
                )}
            </div>

            <div
                style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 6,
                    alignItems: 'center',
                }}
            >
                {events.map((ev, idx) => {
                    const active = Math.abs(cursorT - ev.t) < 90_000 || (ev.kind === 'now' && scrubT === null);
                    return (
                        <button
                            key={`${ev.kind}-${ev.t}`}
                            type="button"
                            onClick={() => jumpToEvent(ev, idx)}
                            className="mono"
                            style={{
                                fontSize: 8.5,
                                letterSpacing: '0.12em',
                                padding: '3px 7px',
                                borderRadius: 3,
                                border: `1px solid ${active ? 'var(--sl-ok)' : 'var(--sl-border)'}`,
                                background: active ? 'var(--sl-ok-soft)' : 'var(--sl-bg-2)',
                                color: active ? 'var(--sl-ok)' : 'var(--sl-text-dim2)',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                            }}
                        >
                            ◉ {ev.label}
                        </button>
                    );
                })}
            </div>

            <div
                ref={trackRef}
                className="sl-scrub-track sl-event-rail"
                role="slider"
                tabIndex={0}
                aria-valuenow={cursorT}
                onMouseDown={onMouseDown}
                onTouchStart={(e) => pickFromClientX(e.touches[0].clientX)}
                onTouchMove={(e) => pickFromClientX(e.touches[0].clientX)}
                style={{ position: 'relative', height: floating ? 22 : 28, cursor: 'pointer', userSelect: 'none' }}
            >
                {segmentLayout.map(({ seg, left, width }, i) =>
                    seg.type === 'gap' ? (
                        <div
                            key={`gap-${i}`}
                            title={seg.label}
                            style={{
                                position: 'absolute',
                                left: `${left}%`,
                                width: `${width}%`,
                                top: '50%',
                                transform: 'translateY(-50%)',
                                height: 14,
                                minWidth: 28,
                                maxWidth: 72,
                                borderRadius: 2,
                                background: 'repeating-linear-gradient(90deg, var(--sl-text-dim3) 0 2px, transparent 2px 5px)',
                                border: '1px solid var(--sl-border)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                overflow: 'hidden',
                            }}
                        >
                            <span
                                className="mono"
                                style={{
                                    fontSize: 7,
                                    color: 'var(--sl-text-dim3)',
                                    letterSpacing: '0.04em',
                                    whiteSpace: 'nowrap',
                                    padding: '0 3px',
                                }}
                            >
                                {seg.label}
                            </span>
                        </div>
                    ) : (
                        <div
                            key={`sig-${i}`}
                            style={{
                                position: 'absolute',
                                left: `${left}%`,
                                width: `${width}%`,
                                top: 'calc(50% - 2px)',
                                height: 4,
                                borderRadius: 2,
                                background: 'var(--sl-bg-2)',
                                border: '1px solid var(--sl-border-hi)',
                            }}
                        />
                    ),
                )}

                {eventPositions.map(({ ev, left }) => (
                    <div
                        key={`tick-${ev.kind}`}
                        title={ev.label}
                        style={{
                            position: 'absolute',
                            left: `${Math.max(0, Math.min(99, left))}%`,
                            top: 'calc(50% - 4px)',
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            background: 'var(--sl-chrome-paper)',
                            border: '2px solid var(--sl-ok)',
                            transform: 'translateX(-50%)',
                            pointerEvents: 'none',
                        }}
                    />
                ))}

                <div
                    className="sl-scrub-thumb"
                    style={{
                        position: 'absolute',
                        top: 'calc(50% - 7px)',
                        left: `${Math.max(1, Math.min(99, focusIdx != null ? ((cursorT - events[focusIdx].t) / (events[focusIdx + 1].t - events[focusIdx].t || 1)) * 100 : cursorFrac * 100))}%`,
                        width: 6,
                        height: 14,
                        borderRadius: 3,
                        background: 'var(--sl-ok)',
                        border: '2px solid var(--sl-chrome-paper)',
                        transform: 'translateX(-50%)',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                    }}
                />
            </div>

            {!floating && (
                <div
                    className="mono"
                    style={{
                        marginTop: 4,
                        fontSize: 9,
                        color: 'var(--sl-text-dim3)',
                        letterSpacing: '0.08em',
                    }}
                >
                    Click a milestone or drag the rail · click the flight path on the map to jump in time
                </div>
            )}
        </div>
    );
}
