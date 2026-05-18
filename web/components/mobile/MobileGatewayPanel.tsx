'use client';

/**
 * Mobile gateway panel — stats + ranked list for the latest uplink.
 * Geographic coverage is shown on the Mapbox layer (orange pins), not here.
 */

import type { GatewayReception } from '../dashboard-v2/atoms';
import { SectionLabel } from './mobileStratolinkUi';
import {
    bearingDeg,
    distanceKm,
    gatewaysWithLocation,
    rssiBarFill,
    rssiTierLabel,
} from './mobileGatewayGeo';

interface MobileGatewayPanelProps {
    gateways: GatewayReception[] | null;
    balloonLat: number | null;
    balloonLon: number | null;
}

function rssiTierColor(rssi: number | null): string {
    if (rssi == null || !Number.isFinite(rssi)) return 'var(--text-dim3)';
    if (rssi >= -85) return '#5eead4';
    if (rssi >= -100) return '#a3e635';
    if (rssi >= -110) return '#fbbf24';
    if (rssi >= -125) return '#f59e0b';
    return '#ef4444';
}

export default function MobileGatewayPanel({
    gateways,
    balloonLat,
    balloonLon,
}: MobileGatewayPanelProps) {
    if (!gateways || gateways.length === 0) {
        return (
            <>
                <SectionLabel>Gateways</SectionLabel>
                <div
                    style={{
                        margin: '4px 20px 16px',
                        padding: 14,
                        border: '1px solid var(--border)',
                        fontFamily: 'var(--sans)',
                        fontSize: 11,
                        color: 'var(--text-dim2)',
                    }}>
                    Awaiting first uplink with rx_metadata.
                </div>
            </>
        );
    }

    const sorted = [...gateways].sort((a, b) => {
        if (a.rssi == null && b.rssi == null) return 0;
        if (a.rssi == null) return 1;
        if (b.rssi == null) return -1;
        return b.rssi - a.rssi;
    });

    const located = gatewaysWithLocation(sorted);
    const count = sorted.length;
    const knownCount = located.length;
    const bestRssi = sorted.find((g) => g.rssi != null)?.rssi ?? null;
    const bestSnr = sorted
        .map((g) => g.snr)
        .filter((v): v is number => v != null && Number.isFinite(v))
        .sort((a, b) => b - a)[0] ?? null;

    const listed = sorted.slice(0, 8);
    const overflow = sorted.length - listed.length;

    return (
        <>
            <SectionLabel
                right={
                    <span
                        style={{
                            fontFamily: 'var(--mono)',
                            fontSize: 10,
                            color: 'var(--text-dim2)',
                            fontVariantNumeric: 'tabular-nums',
                        }}>
                        {bestRssi != null ? `BEST ${Math.round(bestRssi)} dBm` : '—'}
                    </span>
                }>
                Gateways · {count}
            </SectionLabel>

            <div
                style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    borderTop: '1px solid var(--border)',
                    borderBottom: '1px solid var(--border)',
                    fontFamily: 'var(--sans)',
                }}>
                <StatTile
                    label="Count"
                    value={String(count)}
                    sub={knownCount === count ? 'all on map' : `${knownCount} on map`}
                    rightBorder
                />
                <StatTile
                    label="Best RSSI"
                    value={bestRssi != null ? `${Math.round(bestRssi)}` : '—'}
                    suffix=" dBm"
                    sub={bestRssi != null ? rssiTierLabel(bestRssi) : ''}
                    rightBorder
                />
                <StatTile
                    label="Best SNR"
                    value={bestSnr != null ? bestSnr.toFixed(1) : '—'}
                    suffix=" dB"
                    sub={bestSnr != null && bestSnr > 0 ? 'above noise' : 'below noise'}
                />
            </div>

            <div>
                {listed.map((g, i) => (
                    <GatewayRow
                        key={`${g.gateway_id}-${i}`}
                        rank={i + 1}
                        g={g}
                        balloonLat={balloonLat}
                        balloonLon={balloonLon}
                    />
                ))}
                {overflow > 0 && (
                    <div
                        style={{
                            padding: '12px 20px',
                            borderBottom: '1px solid var(--border)',
                            fontFamily: 'var(--sans)',
                            fontSize: 11,
                            color: 'var(--text-dim2)',
                            textAlign: 'center',
                        }}>
                        +{overflow} more receiving gateways
                    </div>
                )}
            </div>
        </>
    );
}

function StatTile({
    label,
    value,
    suffix,
    sub,
    rightBorder,
}: {
    label: string;
    value: string;
    suffix?: string;
    sub?: string;
    rightBorder?: boolean;
}) {
    return (
        <div
            style={{
                padding: '14px 16px',
                borderRight: rightBorder ? '1px solid var(--border)' : undefined,
            }}>
            <div
                style={{
                    fontFamily: 'var(--sans)',
                    fontSize: 9,
                    letterSpacing: '0.14em',
                    color: 'var(--text-dim2)',
                    textTransform: 'uppercase',
                    fontWeight: 500,
                    marginBottom: 6,
                }}>
                {label}
            </div>
            <div
                style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 18,
                    fontWeight: 500,
                    color: 'var(--text-hi)',
                    lineHeight: 1,
                    fontVariantNumeric: 'tabular-nums',
                }}>
                {value}
                {suffix ? <span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>{suffix}</span> : null}
            </div>
            {sub ? (
                <div
                    style={{
                        marginTop: 6,
                        fontFamily: 'var(--sans)',
                        fontSize: 10,
                        color: 'var(--text-dim2)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                    }}>
                    {sub}
                </div>
            ) : null}
        </div>
    );
}

function GatewayRow({
    rank,
    g,
    balloonLat,
    balloonLon,
}: {
    rank: number;
    g: GatewayReception;
    balloonLat: number | null;
    balloonLon: number | null;
}) {
    const color = rssiTierColor(g.rssi);
    const display = g.gateway_id.length > 24 ? `…${g.gateway_id.slice(-20)}` : g.gateway_id;

    let dist: number | null = null;
    let bearing: number | null = null;
    if (balloonLat != null && balloonLon != null && g.lat != null && g.lon != null) {
        dist = distanceKm(balloonLat, balloonLon, g.lat, g.lon);
        bearing = bearingDeg(balloonLat, balloonLon, g.lat, g.lon);
    }

    const pct = rssiBarFill(g.rssi);

    return (
        <div
            style={{
                padding: '12px 20px',
                borderBottom: '1px solid var(--border)',
                fontFamily: 'var(--sans)',
            }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                <span
                    style={{
                        fontFamily: 'var(--mono)',
                        fontSize: 10,
                        color: 'var(--text-dim3)',
                        fontVariantNumeric: 'tabular-nums',
                        minWidth: 16,
                    }}>
                    {String(rank).padStart(2, '0')}
                </span>
                <span
                    style={{
                        fontFamily: 'var(--mono)',
                        fontSize: 11,
                        color: 'var(--text-hi)',
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                    }}>
                    {display}
                </span>
                <span
                    style={{
                        fontFamily: 'var(--mono)',
                        fontSize: 12,
                        color: 'var(--text-hi)',
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 500,
                    }}>
                    {g.rssi != null ? `${Math.round(g.rssi)}` : '—'}
                    <span style={{ fontSize: 9, color: 'var(--text-dim3)', marginLeft: 2 }}>dBm</span>
                </span>
            </div>

            <div
                style={{
                    marginTop: 6,
                    height: 3,
                    background: 'rgba(255,255,255,0.05)',
                    position: 'relative',
                }}>
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        right: `${(1 - pct) * 100}%`,
                        background: color,
                    }}
                />
            </div>

            <div
                style={{
                    marginTop: 6,
                    display: 'flex',
                    gap: 12,
                    fontFamily: 'var(--mono)',
                    fontSize: 9,
                    color: 'var(--text-dim2)',
                    fontVariantNumeric: 'tabular-nums',
                }}>
                {g.snr != null ? <span>SNR {g.snr.toFixed(1)} dB</span> : <span style={{ opacity: 0.4 }}>SNR —</span>}
                {dist != null && bearing != null ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <BearingArrow deg={bearing} />
                        {dist >= 100 ? `${Math.round(dist)} km` : `${dist.toFixed(1)} km`}
                    </span>
                ) : (
                    <span style={{ opacity: 0.4 }}>no location</span>
                )}
            </div>
        </div>
    );
}

function BearingArrow({ deg }: { deg: number }) {
    return (
        <svg width={10} height={10} viewBox="0 0 10 10" style={{ display: 'inline-block' }}>
            <g transform={`rotate(${deg.toFixed(1)} 5 5)`}>
                <path d="M5 1 L8 8 L5 6.5 L2 8 Z" fill="var(--text-dim)" />
            </g>
        </svg>
    );
}
