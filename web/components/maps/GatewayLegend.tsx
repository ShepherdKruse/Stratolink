/**
 * Small map legend explaining the TTN coverage outlines.
 *
 * Sits as an absolutely-positioned overlay inside a map container.
 * Default placement is bottom-right; override via the `placement` prop
 * if another legend's there.
 */
'use client';

import type { CSSProperties } from 'react';

export interface GatewayLegendProps {
    /** Corner to mount in. */
    placement?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    /** Defaults to true. */
    visible?: boolean;
}

/* `bottom: 30` clears the Mapbox attribution bar that always sits at
 * `bottom: 0` on the same side of the map (~22 px tall + 8 px gap). */
const PLACEMENT_STYLES: Record<NonNullable<GatewayLegendProps['placement']>, CSSProperties> = {
    'top-left':     { top: 12, left: 12 },
    'top-right':    { top: 12, right: 12 },
    'bottom-left':  { bottom: 30, left: 12 },
    'bottom-right': { bottom: 30, right: 12 },
};

export default function GatewayLegend({
    placement = 'bottom-right',
    visible = true,
}: GatewayLegendProps) {
    if (!visible) return null;
    return (
        <div
            style={{
                position: 'absolute',
                ...PLACEMENT_STYLES[placement],
                zIndex: 5,
                pointerEvents: 'none',
                background: 'rgba(8, 13, 23, 0.78)',
                backdropFilter: 'blur(6px)',
                WebkitBackdropFilter: 'blur(6px)',
                border: '1px solid rgba(94, 234, 212, 0.12)',
                borderRadius: 4,
                padding: '8px 10px',
                fontFamily: 'var(--sl-sans, system-ui, sans-serif)',
                fontSize: 10.5,
                color: 'rgba(200, 212, 232, 0.78)',
                lineHeight: 1.3,
                minWidth: 132,
            }}
        >
            <div style={{
                fontSize: 9,
                letterSpacing: '0.10em',
                textTransform: 'uppercase',
                color: 'rgba(200, 212, 232, 0.45)',
                marginBottom: 6,
            }}>
                TTN Coverage
            </div>

            {/* 150 km — solid outline + faint fill */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
                <span
                    aria-hidden
                    style={{
                        display: 'inline-block',
                        width: 18,
                        height: 10,
                        background: 'rgba(94, 234, 212, 0.10)',
                        border: '1px solid rgba(94, 234, 212, 0.55)',
                        borderRadius: 1,
                    }}
                />
                <span>150 km · in range</span>
            </div>

            {/* 250 km — dashed outline only */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span
                    aria-hidden
                    style={{
                        display: 'inline-block',
                        width: 18,
                        height: 10,
                        borderTop: '1.5px dashed rgba(94, 234, 212, 0.6)',
                        borderRadius: 0,
                    }}
                />
                <span>250 km · line-of-sight</span>
            </div>
        </div>
    );
}
