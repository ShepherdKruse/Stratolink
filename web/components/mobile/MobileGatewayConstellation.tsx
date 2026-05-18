'use client';

/**
 * Mobile gateway constellation.
 *
 * The desktop dashboard already lists gateways in a right-rail panel and pins
 * them on the Mapbox layer. On mobile we don't have the screen real estate for
 * either pattern, so this component takes a different angle: it renders a
 * single polar plot ("constellation") that captures both *coverage geometry*
 * and *signal strength* in one glance — answering the two questions an
 * operator actually asks while a balloon is in the air:
 *
 *   1. Is the balloon being heard from many directions, or only one side?
 *      → spread of dots around the compass.
 *   2. How strong is each reception?
 *      → distance from center (closer = stronger) and color tier.
 *
 * The plot is followed by a stat row and a ranked list with mini RSSI bars,
 * distance, and bearing arrows so the operator can drill into individual
 * gateways without leaving the screen.
 *
 * Anonymous gateways — those routed via TTN's Packet Broker, which strips
 * coordinates — are still meaningful (they prove someone heard the packet),
 * so we plot them on a faint outer "no-bearing" ring rather than dropping
 * them entirely.
 */

import type { GatewayReception } from '../dashboard-v2/atoms';
import { SectionLabel } from './mobileStratolinkUi';

interface MobileGatewayConstellationProps {
    gateways: GatewayReception[] | null;
    /** Balloon's last known position. Used to compute bearing/distance to
     *  each gateway with a known location. May be null shortly after a
     *  power-on before GPS lock. */
    balloonLat: number | null;
    balloonLon: number | null;
}

/* ──────────────────────────────────────────────────────────────
 * RSSI tiering — mirrors the V2MissionMap line-color/circle-color
 * gradients. Mobile uses discrete buckets instead of an interpolated
 * gradient because anti-aliased dots beat smooth gradients on a small
 * screen. The breakpoints come from typical pico-balloon link budgets
 * at LoRa SF7-SF10 with 125 kHz BW: −85 dBm is solid coverage, −110
 * dBm is the marginal-but-decoded floor at SF10/CR4-5.
 * ────────────────────────────────────────────────────────────── */
function rssiTierColor(rssi: number | null): string {
    if (rssi == null || !Number.isFinite(rssi)) return 'var(--text-dim3)';
    if (rssi >= -85) return '#5eead4';
    if (rssi >= -100) return '#a3e635';
    if (rssi >= -110) return '#fbbf24';
    if (rssi >= -125) return '#f59e0b';
    return '#ef4444';
}

/* Range-ring breakpoints (dBm). Drawn from inside out — strongest to
 * weakest. The radial scale is calibrated so −85 dBm sits near the
 * center crosshair and −125 dBm rides the outer ring; readings outside
 * that band clamp to the edges. */
const RING_DBM = [-85, -100, -110, -125] as const;

/** Convert RSSI to a normalized [0..1] radius where 0 = center,
 *  1 = outer ring. Strong RSSI → small radius. */
function rssiToRadius(rssi: number | null): number {
    if (rssi == null || !Number.isFinite(rssi)) return 0.95;
    const lo = -125;
    const hi = -85;
    const clamped = Math.max(lo, Math.min(hi, rssi));
    return (hi - clamped) / (hi - lo);
}

/** Initial bearing (degrees, 0 = north, clockwise) from balloon to gateway.
 *  Standard great-circle formula; accurate enough for sub-100 km hops. */
function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const Δλ = ((lon2 - lon1) * Math.PI) / 180;
    const y = Math.sin(Δλ) * Math.cos(φ2);
    const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
    const θ = Math.atan2(y, x);
    return ((θ * 180) / Math.PI + 360) % 360;
}

/** Haversine distance in km. */
function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const dφ = ((lat2 - lat1) * Math.PI) / 180;
    const dλ = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(dλ / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

interface PlottedGateway {
    g: GatewayReception;
    /** SVG x in viewBox coords (0..VB), null if anonymous. */
    x: number | null;
    y: number | null;
    /** Same data computed once so the list renders consistently with the dot. */
    bearing: number | null;
    distanceKm: number | null;
}

/* ──────────────────────────────────────────────────────────────
 * Plot constants. Kept module-level so the layout can't drift between
 * the SVG and the legend math.
 * ────────────────────────────────────────────────────────────── */
const VB = 320; /* viewBox is square; SVG scales via width="100%" */
const CX = VB / 2;
const CY = VB / 2;
const R_OUTER = 130; /* outermost ring radius in viewBox units */
const R_ANON = 148; /* anonymous-gateway ring sits just outside the rings */

export default function MobileGatewayConstellation({
    gateways,
    balloonLat,
    balloonLon,
}: MobileGatewayConstellationProps) {
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

    /* Strongest-first sort. Null RSSI sinks to the bottom. */
    const sorted = [...gateways].sort((a, b) => {
        if (a.rssi == null && b.rssi == null) return 0;
        if (a.rssi == null) return 1;
        if (b.rssi == null) return -1;
        return b.rssi - a.rssi;
    });

    const haveBalloonPos =
        balloonLat != null &&
        balloonLon != null &&
        Number.isFinite(balloonLat) &&
        Number.isFinite(balloonLon);

    /* Lay out anonymous gateways evenly around the outer "unknown" ring
     * so they read as "we heard you, we just don't know from where". */
    const anonymousList = sorted.filter(
        (g) => !haveBalloonPos || g.lat == null || g.lon == null,
    );
    const anonStep = anonymousList.length > 0 ? 360 / anonymousList.length : 0;
    let anonIndex = 0;

    const plotted: PlottedGateway[] = sorted.map((g) => {
        if (haveBalloonPos && g.lat != null && g.lon != null) {
            const bearing = bearingDeg(balloonLat, balloonLon, g.lat, g.lon);
            const dist = distanceKm(balloonLat, balloonLon, g.lat, g.lon);
            const r = rssiToRadius(g.rssi) * R_OUTER;
            /* In SVG y grows downward, so subtract sin(bearing) instead of
             * adding it for the cardinal angle convention (0 = up = north). */
            const θ = (bearing * Math.PI) / 180;
            const x = CX + Math.sin(θ) * r;
            const y = CY - Math.cos(θ) * r;
            return { g, x, y, bearing, distanceKm: dist };
        }
        const slot = anonIndex++;
        const bearing = slot * anonStep;
        const θ = (bearing * Math.PI) / 180;
        const x = CX + Math.sin(θ) * R_ANON;
        const y = CY - Math.cos(θ) * R_ANON;
        return { g, x, y, bearing: null, distanceKm: null };
    });

    const count = sorted.length;
    const knownCount = plotted.filter((p) => p.bearing !== null).length;
    const bestRssi = sorted.find((g) => g.rssi != null)?.rssi ?? null;
    const bestSnr = sorted
        .map((g) => g.snr)
        .filter((v): v is number => v != null && Number.isFinite(v))
        .sort((a, b) => b - a)[0] ?? null;

    /* List is capped at 8 — beyond that the rows stop being individually
     * actionable on a phone. The full list still rides on every uplink in
     * the JSONB column. */
    const listed = sorted.slice(0, 8);
    const overflow = sorted.length - listed.length;

    /* Map plotted gateways back to their index for hover/tap synchrony.
     * (A future tap-to-highlight gesture lives on this index.) */
    const ringRadii = RING_DBM.map((dbm) => rssiToRadius(dbm) * R_OUTER);

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
                    padding: '6px 16px 12px',
                    fontFamily: 'var(--sans)',
                }}>
                <svg
                    width="100%"
                    viewBox={`0 0 ${VB} ${VB}`}
                    style={{ display: 'block', maxWidth: 360, margin: '0 auto' }}
                    aria-label="Gateway coverage constellation">
                    {/* Range rings (dashed) — labelled with their dBm threshold. */}
                    {ringRadii.map((r, i) => (
                        <g key={`ring-${i}`}>
                            <circle
                                cx={CX}
                                cy={CY}
                                r={r}
                                fill="none"
                                stroke="var(--border-hi)"
                                strokeOpacity={0.55}
                                strokeWidth={0.6}
                                strokeDasharray="3 4"
                            />
                            <text
                                x={CX + r + 4}
                                y={CY - 2}
                                style={{
                                    fontFamily: 'var(--mono)',
                                    fontSize: 8,
                                    fill: 'var(--text-dim3)',
                                    fontVariantNumeric: 'tabular-nums',
                                }}>
                                {RING_DBM[i]}
                            </text>
                        </g>
                    ))}

                    {/* Anonymous-gateway band — drawn distinctly so the eye reads it
                      * as "heard, location unknown" rather than "extremely far". */}
                    {anonymousList.length > 0 && (
                        <circle
                            cx={CX}
                            cy={CY}
                            r={R_ANON}
                            fill="none"
                            stroke="var(--border-hi)"
                            strokeOpacity={0.25}
                            strokeWidth={0.5}
                            strokeDasharray="1 3"
                        />
                    )}

                    {/* Cardinal marks — N/E/S/W. */}
                    {[
                        { label: 'N', x: CX, y: CY - R_ANON - 8, anchor: 'middle' as const },
                        { label: 'E', x: CX + R_ANON + 10, y: CY + 3, anchor: 'start' as const },
                        { label: 'S', x: CX, y: CY + R_ANON + 14, anchor: 'middle' as const },
                        { label: 'W', x: CX - R_ANON - 10, y: CY + 3, anchor: 'end' as const },
                    ].map((c) => (
                        <text
                            key={c.label}
                            x={c.x}
                            y={c.y}
                            textAnchor={c.anchor}
                            style={{
                                fontFamily: 'var(--sans)',
                                fontSize: 10,
                                fill: 'var(--text-dim2)',
                                letterSpacing: '0.1em',
                                fontWeight: 500,
                            }}>
                            {c.label}
                        </text>
                    ))}

                    {/* Sight lines from balloon to each known-bearing gateway —
                      * the visual cue that "this packet was decoded at that pin".
                      * Drawn beneath dots so the dots win the z-order. */}
                    {plotted.map((p, i) =>
                        p.x !== null && p.y !== null && p.bearing !== null ? (
                            <line
                                key={`l-${i}`}
                                x1={CX}
                                y1={CY}
                                x2={p.x}
                                y2={p.y}
                                stroke={rssiTierColor(p.g.rssi)}
                                strokeOpacity={0.18}
                                strokeWidth={0.7}
                            />
                        ) : null,
                    )}

                    {/* Center crosshair representing the balloon. */}
                    <g>
                        <line x1={CX - 8} y1={CY} x2={CX - 3} y2={CY} stroke="var(--ok)" strokeWidth={1} />
                        <line x1={CX + 3} y1={CY} x2={CX + 8} y2={CY} stroke="var(--ok)" strokeWidth={1} />
                        <line x1={CX} y1={CY - 8} x2={CX} y2={CY - 3} stroke="var(--ok)" strokeWidth={1} />
                        <line x1={CX} y1={CY + 3} x2={CX} y2={CY + 8} stroke="var(--ok)" strokeWidth={1} />
                        <circle cx={CX} cy={CY} r={2} fill="var(--ok)" />
                    </g>

                    {/* Gateway dots. The strongest gateway gets a halo + ID badge so
                      * the operator can identify "the one carrying the link" without
                      * scanning the list. */}
                    {plotted.map((p, i) => {
                        if (p.x === null || p.y === null) return null;
                        const isStrongest = i === 0;
                        const known = p.bearing !== null;
                        const color = rssiTierColor(p.g.rssi);
                        return (
                            <g key={`gw-${i}-${p.g.gateway_id}`}>
                                {isStrongest && (
                                    <circle
                                        cx={p.x}
                                        cy={p.y}
                                        r={7}
                                        fill="none"
                                        stroke={color}
                                        strokeOpacity={0.5}
                                        strokeWidth={1}
                                    />
                                )}
                                <circle
                                    cx={p.x}
                                    cy={p.y}
                                    r={known ? 3.4 : 2.2}
                                    fill={color}
                                    fillOpacity={known ? 0.95 : 0.55}
                                />
                            </g>
                        );
                    })}
                </svg>

                {/* Legend strip — colour swatches matched to the same tiering as
                  * the dots. Dimensions chosen to align under the SVG nicely on a
                  * 360 px-wide phone. */}
                <div
                    style={{
                        marginTop: 8,
                        display: 'flex',
                        gap: 10,
                        flexWrap: 'wrap',
                        fontFamily: 'var(--mono)',
                        fontSize: 9,
                        color: 'var(--text-dim2)',
                        justifyContent: 'center',
                    }}>
                    <LegendDot color="#5eead4" label="≥−85" />
                    <LegendDot color="#a3e635" label="−85…−100" />
                    <LegendDot color="#fbbf24" label="−100…−110" />
                    <LegendDot color="#f59e0b" label="−110…−125" />
                    {anonymousList.length > 0 && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ display: 'inline-block', width: 10, height: 1, background: 'var(--text-dim3)' }} />
                            no loc · {anonymousList.length}
                        </span>
                    )}
                </div>
            </div>

            {/* Compact stat row — count, best RSSI, best SNR. */}
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
                    sub={knownCount === count ? 'all located' : `${knownCount} located`}
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

            {/* Ranked list — RSSI bar gives the same info the dot's radial
              * position does, but in a one-dimensional layout that's faster
              * to scan when there are many gateways. */}
            <div>
                {listed.map((g, i) => (
                    <GatewayRow key={`${g.gateway_id}-${i}`} rank={i + 1} g={g} balloonLat={balloonLat} balloonLon={balloonLon} />
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

function rssiTierLabel(rssi: number): string {
    if (rssi >= -85) return 'strong';
    if (rssi >= -100) return 'good';
    if (rssi >= -110) return 'fair';
    if (rssi >= -125) return 'weak';
    return 'marginal';
}

function LegendDot({ color, label }: { color: string; label: string }) {
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span
                style={{
                    display: 'inline-block',
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: color,
                }}
            />
            {label}
        </span>
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

    /* Truncate from the front — TTN gateway IDs share a long "eui-" prefix and
     * the discriminating bytes live at the tail. */
    const display =
        g.gateway_id.length > 24 ? `…${g.gateway_id.slice(-20)}` : g.gateway_id;

    let dist: number | null = null;
    let bearing: number | null = null;
    if (
        balloonLat != null &&
        balloonLon != null &&
        g.lat != null &&
        g.lon != null
    ) {
        dist = distanceKm(balloonLat, balloonLon, g.lat, g.lon);
        bearing = bearingDeg(balloonLat, balloonLon, g.lat, g.lon);
    }

    /* RSSI bar fill. Use the same radial scaling as the constellation so the
     * bar and the dot agree visually. */
    const filled = 1 - rssiToRadius(g.rssi);
    const pct = Math.max(0.04, Math.min(1, filled));

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

            {/* RSSI bar — lives just under the row so the eye scans down the
              * column of bars without re-anchoring. */}
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

/** A tiny upward-pointing chevron rotated to the bearing. Drawn inline in the
 *  row so distance + direction read together. */
function BearingArrow({ deg }: { deg: number }) {
    return (
        <svg width={10} height={10} viewBox="0 0 10 10" style={{ display: 'inline-block' }}>
            <g transform={`rotate(${deg.toFixed(1)} 5 5)`}>
                <path d="M5 1 L8 8 L5 6.5 L2 8 Z" fill="var(--text-dim)" />
            </g>
        </svg>
    );
}
