'use client';

import { useMemo, type CSSProperties } from 'react';
import {
    formatTimelineRelLabel,
    formatTimelineUtc,
    haversineKm,
    type ForecastTimeline,
    type TimelinePosition,
} from '@/lib/wind/forecastTimeline';

export type ReconstructionGapInfo = {
    dt_hours: number;
    measured_altitude: boolean;
    endpoint_miss_km: number;
    mid_gap_90_km: number;
    confidence: string;
    mode?: 'line' | 'corridor';
    n_eff?: number;
};

type WindForecastScrubberProps = {
    timeline: ForecastTimeline;
    scrubMs: number;
    onScrubMs: (t: number) => void;
    position: TimelinePosition | null;
    observedTrack: Array<{ lat: number; lon: number; t: number }>;
    forecastHorizonH: number;
    reconstructionGap?: ReconstructionGapInfo | null;
};

function fmtCoord(lat: number, lon: number): string {
    const ns = lat >= 0 ? 'N' : 'S';
    const ew = lon >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(2)}°${ns} ${Math.abs(lon).toFixed(2)}°${ew}`;
}

export default function WindForecastScrubber({
    timeline,
    scrubMs,
    onScrubMs,
    position,
    observedTrack,
    forecastHorizonH,
    reconstructionGap,
}: WindForecastScrubberProps) {
    const { tMin, tMax, tLastFix, tNow } = timeline;
    const scrubPct =
        tMax > tMin ? Math.max(0, Math.min(100, ((scrubMs - tMin) / (tMax - tMin)) * 100)) : 0;

    const ticks = useMemo(() => {
        const items: Array<{ t: number; label: string }> = [
            { t: tLastFix, label: 'Last GPS' },
            { t: tNow, label: 'Now' },
        ];
        for (const h of [6, 12, 18, 24]) {
            if (h <= forecastHorizonH) {
                items.push({ t: tNow + h * 3_600_000, label: `+${h}h` });
            }
        }
        return items.filter((x) => x.t >= tMin && x.t <= tMax);
    }, [tMin, tMax, tLastFix, tNow, forecastHorizonH]);

    const gapHint = useMemo(() => {
        if (!position || position.segment !== 'gap') return null;
        const last = observedTrack.length ? observedTrack[observedTrack.length - 1] : null;
        if (!last) return 'No GPS in this period — position is model dead-reckoning only.';
        const km = haversineKm(position.lat, position.lon, last.lat, last.lon);
        return `No GPS in this period — model implied position is ${Math.round(km)} km from the last recorded fix.`;
    }, [position, observedTrack]);

    return (
        <div className="wind-synthesis-scrubber">
            <div className="wind-synthesis-scrubber-head">
                <div className="wind-synthesis-scrubber-title">Time along track</div>
                <button type="button" className="wind-synthesis-scrubber-now" onClick={() => onScrubMs(tNow)}>
                    Jump to now
                </button>
            </div>

            {position && (
                <div className="wind-synthesis-scrubber-meta">
                    <span className="wind-synthesis-scrubber-seg">
                        {formatTimelineRelLabel(position.relHours, position.segment)}
                    </span>
                    <span className="wind-synthesis-scrubber-time">{formatTimelineUtc(scrubMs)} UTC</span>
                    <span className="wind-synthesis-scrubber-coord">{fmtCoord(position.lat, position.lon)}</span>
                    {position.segment === 'observed' && (
                        <span className="wind-synthesis-scrubber-hint">
                            Recorded GPS (ground truth).{' '}
                            {reconstructionGap && (
                                <>
                                    {reconstructionGap.mode === 'corridor' ? (
                                        <>
                                            <strong>Amber region</strong> = reachability corridor for this{' '}
                                            {reconstructionGap.dt_hours}h GPS gap (under-determined, n_eff≈
                                            {reconstructionGap.n_eff ?? '—'}). Mid-gap uncertainty ±
                                            {reconstructionGap.mid_gap_90_km} km.
                                        </>
                                    ) : (
                                        <>
                                            <strong>Cyan dashed line</strong> = reconstructed path through this{' '}
                                            {reconstructionGap.dt_hours}h GPS gap ({reconstructionGap.confidence}{' '}
                                            confidence, ±{reconstructionGap.mid_gap_90_km} km mid-gap
                                            {reconstructionGap.measured_altitude ? ', baro altitude' : ''}).
                                            Endpoint miss {reconstructionGap.endpoint_miss_km} km.
                                        </>
                                    )}
                                </>
                            )}
                        </span>
                    )}
                    {gapHint && <span className="wind-synthesis-scrubber-hint">{gapHint}</span>}
                    {position.segment === 'forecast' && position.relHours > 0 && (
                        <span className="wind-synthesis-scrubber-hint">
                            Monte Carlo nominal path · ellipses show uncertainty at +6h … +{forecastHorizonH}h.
                        </span>
                    )}
                </div>
            )}

            <p className="wind-synthesis-scrubber-drag-hint">Drag the handle along the timeline</p>
            <div
                className="wind-synthesis-scrubber-track-wrap"
                style={{ '--scrub-pct': `${scrubPct}%` } as CSSProperties}
            >
                <div className="wind-synthesis-scrubber-zones">
                    <div
                        className="wind-synthesis-scrubber-zone observed"
                        style={{
                            left: 0,
                            width: `${((tLastFix - tMin) / (tMax - tMin)) * 100}%`,
                        }}
                        title="Observed GPS"
                    />
                    {timeline.hasGap && (
                        <div
                            className="wind-synthesis-scrubber-zone gap"
                            style={{
                                left: `${((tLastFix - tMin) / (tMax - tMin)) * 100}%`,
                                width: `${((tNow - tLastFix) / (tMax - tMin)) * 100}%`,
                            }}
                            title="Implied drift (no GPS)"
                        />
                    )}
                    <div
                        className="wind-synthesis-scrubber-zone forecast"
                        style={{
                            left: `${((tNow - tMin) / (tMax - tMin)) * 100}%`,
                            width: `${((tMax - tNow) / (tMax - tMin)) * 100}%`,
                        }}
                        title="Forward forecast"
                    />
                </div>
                <div className="wind-synthesis-scrubber-playhead" aria-hidden />
                <input
                    type="range"
                    className="wind-synthesis-scrubber-range"
                    min={tMin}
                    max={tMax}
                    step={60_000}
                    value={scrubMs}
                    onChange={(e) => onScrubMs(Number(e.target.value))}
                    aria-label="Drag to move balloon along observed track and forecast"
                    aria-valuetext={`${formatTimelineUtc(scrubMs)} UTC`}
                />
                <div className="wind-synthesis-scrubber-ticks">
                    {ticks.map((tick) => (
                        <button
                            key={tick.t}
                            type="button"
                            className="wind-synthesis-scrubber-tick"
                            style={{ left: `${((tick.t - tMin) / (tMax - tMin)) * 100}%` }}
                            onClick={() => onScrubMs(tick.t)}
                        >
                            {tick.label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
