/**
 * Overlay for the balloon-centered gateway range view.
 *
 * Renders, bottom-left of the map: a RANGE RINGS toggle, the plain-language
 * signal readout (the actual answer — "expect signal" / "marginal" /
 * "silence"), and, when rings are shown, a small legend.
 *
 * Self-contained: loads the gateway points and derives the nearest-gateway
 * distance + readout from the passed balloon position. Position is absolute,
 * so drop it inside the (relative) map container.
 */
'use client';

import { useMemo } from 'react';
import { useGatewayPoints } from '@/lib/gateways/data';
import { nearestGateway, signalReadout, type SignalChip } from '@/lib/gateways/range';

const CHIP_STYLE: Record<SignalChip, { color: string; border: string; bg: string }> = {
    ok: { color: '#6fe0c8', border: 'rgba(95,212,188,0.4)', bg: 'rgba(63,184,160,0.08)' },
    maybe: { color: '#e6b450', border: 'rgba(230,180,80,0.4)', bg: 'rgba(230,180,80,0.08)' },
    none: { color: '#e08a6a', border: 'rgba(224,138,90,0.4)', bg: 'rgba(224,138,90,0.08)' },
};

export interface GatewayRangeControlsProps {
    lat: number;
    lon: number;
    altM: number | null;
    rangeMode: boolean;
    onToggle: () => void;
}

export default function GatewayRangeControls({ lat, lon, altM, rangeMode, onToggle }: GatewayRangeControlsProps) {
    const points = useGatewayPoints();
    const nearest = useMemo(() => nearestGateway(lat, lon, points), [lat, lon, points]);
    const readout = useMemo(() => signalReadout(nearest?.distKm ?? null, altM), [nearest, altM]);
    const chip = CHIP_STYLE[readout.chip];
    const loading = points.length === 0;

    return (
        <div
            style={{
                position: 'absolute',
                left: 14,
                bottom: 14,
                zIndex: 2,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                maxWidth: 300,
            }}
        >
            <button
                type="button"
                onClick={onToggle}
                aria-pressed={rangeMode}
                style={{
                    alignSelf: 'flex-start',
                    padding: '6px 10px',
                    fontFamily: 'var(--sl-mono, monospace)',
                    fontSize: 10,
                    letterSpacing: '0.10em',
                    textTransform: 'uppercase',
                    color: rangeMode ? '#0b1220' : '#cbd5e1',
                    background: rangeMode ? '#5fd4bc' : 'rgba(11,18,32,0.85)',
                    border: '1px solid ' + (rangeMode ? '#5fd4bc' : '#334155'),
                    cursor: 'pointer',
                    backdropFilter: 'blur(4px)',
                    WebkitBackdropFilter: 'blur(4px)',
                }}
            >
                {rangeMode ? '◉' : '○'} RANGE RINGS
            </button>

            {/* Readout — the actual answer. */}
            <div
                style={{
                    background: 'rgba(8,13,23,0.82)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 9,
                    padding: '10px 12px',
                    backdropFilter: 'blur(8px)',
                    WebkitBackdropFilter: 'blur(8px)',
                }}
            >
                <span
                    style={{
                        display: 'inline-block',
                        fontFamily: 'var(--sl-mono, monospace)',
                        fontSize: 10,
                        letterSpacing: '0.12em',
                        textTransform: 'uppercase',
                        padding: '4px 9px',
                        borderRadius: 5,
                        color: chip.color,
                        background: chip.bg,
                        border: `1px solid ${chip.border}`,
                        marginBottom: 7,
                    }}
                >
                    {loading ? 'LOADING…' : readout.chip === 'ok' ? 'SIGNAL EXPECTED' : readout.chip === 'maybe' ? 'MARGINAL' : 'SILENCE'}
                </span>
                <div style={{ fontSize: 11, lineHeight: 1.45, color: 'rgba(200,212,232,0.85)' }}>
                    {loading ? 'Loading gateway network…' : readout.text}
                </div>
            </div>

            {/* Legend — only while the rings are drawn. */}
            {rangeMode && (
                <div
                    style={{
                        background: 'rgba(8,13,23,0.82)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 9,
                        padding: '12px 14px',
                        backdropFilter: 'blur(8px)',
                        WebkitBackdropFilter: 'blur(8px)',
                    }}
                >
                    <div
                        style={{
                            fontFamily: 'var(--sl-mono, monospace)',
                            fontSize: 9,
                            letterSpacing: '0.2em',
                            textTransform: 'uppercase',
                            color: 'rgba(200,212,232,0.4)',
                            marginBottom: 9,
                        }}
                    >
                        Range to Nearest Gateway
                    </div>
                    <LegendRow ring color="#6fe0c8" dashed={false} label="SF7 range (in use)" />
                    <LegendRow ring color="#4fc8b4" dashed label="SF10 reach (if lowered)" />
                    <LegendRow ring color="#3fb8a0" dashed label="SF12 reach (max range)" />
                    <LegendRow ring={false} color="#6fe0c8" dashed={false} label="Gateway" last />
                </div>
            )}
        </div>
    );
}

function LegendRow({
    ring,
    color,
    dashed,
    label,
    last,
}: {
    ring: boolean;
    color: string;
    dashed: boolean;
    label: string;
    last?: boolean;
}) {
    return (
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                fontSize: 12,
                color: 'rgba(200,212,232,0.6)',
                marginBottom: last ? 0 : 6,
            }}
        >
            {ring ? (
                <span
                    style={{
                        width: 12,
                        height: 12,
                        borderRadius: '50%',
                        border: `1.5px ${dashed ? 'dashed' : 'solid'} ${color}`,
                        display: 'inline-block',
                        flexShrink: 0,
                    }}
                />
            ) : (
                <span
                    style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: color,
                        border: '1px solid rgba(95,212,188,0.5)',
                        display: 'inline-block',
                        flexShrink: 0,
                    }}
                />
            )}
            {label}
        </div>
    );
}
