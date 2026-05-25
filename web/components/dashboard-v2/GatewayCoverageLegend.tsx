/**
 * Legend for the ambient TTN gateway coverage field on the world map.
 *
 * Explains what the teal glow + dots mean and why they matter for a balloon:
 * coverage is where community LoRa gateways can hear an uplink; the dark gaps
 * are where a balloon is likely to go silent. Absolutely positioned — drop it
 * inside a (relative) map container.
 */
'use client';

export default function GatewayCoverageLegend() {
    return (
        <div
            style={{
                position: 'absolute',
                right: 14,
                bottom: 14,
                zIndex: 1,
                width: 210,
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
                    color: 'rgba(200,212,232,0.45)',
                    marginBottom: 10,
                }}
            >
                TTN Gateway Coverage
            </div>

            {/* Density gradient */}
            <div
                style={{
                    height: 8,
                    borderRadius: 3,
                    background:
                        'linear-gradient(90deg, rgba(63,184,160,0.12), rgba(80,200,180,0.32), rgba(120,225,205,0.6))',
                }}
            />
            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 9,
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                    color: 'rgba(200,212,232,0.45)',
                    marginTop: 4,
                    marginBottom: 10,
                }}
            >
                <span>sparse</span>
                <span>dense</span>
            </div>

            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 9,
                    fontSize: 12,
                    color: 'rgba(200,212,232,0.6)',
                    marginBottom: 10,
                }}
            >
                <span
                    style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: '#5fd4bc',
                        border: '1px solid rgba(95,212,188,0.5)',
                        display: 'inline-block',
                        flexShrink: 0,
                    }}
                />
                Gateway (zoom in)
            </div>

            <div style={{ fontSize: 10.5, lineHeight: 1.45, color: 'rgba(200,212,232,0.5)' }}>
                Teal shows where community LoRa gateways can hear an uplink. Over the dark gaps a
                balloon is likely to go silent.
            </div>
        </div>
    );
}
