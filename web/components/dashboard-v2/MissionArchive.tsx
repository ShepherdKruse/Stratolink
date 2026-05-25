/**
 * Mission Archive — the dashboard's catalogue of completed flights.
 *
 * Lists past missions (Supabase devices that have landed/retired, plus
 * curated sample flights) as dark-themed cards with summary KPIs. Each
 * card opens a full per-flight replay at /dashboard-v2/archive/[id].
 *
 * Data discipline mirrors the rest of v2: every number is a real Supabase
 * or curated value, or '—'.
 */
'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Chrome, fmt, DASHBOARD_V2_TABS } from './atoms';
import { useTickingNow, ConnectionPill, V1Link, fmtAltitudeM } from './shared';
import { usePastFlights, type PastFlightSummary } from '@/lib/flights/pastFlights';

export default function MissionArchiveScreen() {
    const router = useRouter();
    const now = useTickingNow();
    const { flights, status, loading } = usePastFlights();

    const latestEnd = flights.reduce<number | null>(
        (acc, f) => (f.endedAtMs !== null && (acc === null || f.endedAtMs > acc) ? f.endedAtMs : acc),
        null,
    );

    return (
        <div className="sl-app" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
            <Chrome
                tabs={DASHBOARD_V2_TABS}
                activePath="/dashboard-v2/archive"
                onNavigate={(path) => router.push(path)}
                lastUplinkT={latestEnd}
                lastFixT={latestEnd}
                now={now}
                right={
                    <>
                        <ConnectionPill status={status} lastFetchedAt={loading ? null : Date.now()} now={now} />
                        <span style={{ color: 'var(--sl-text-dim)', fontSize: 11 }}>archive</span>
                        <V1Link />
                    </>
                }
            />

            {/* Intro strip */}
            <div
                style={{
                    padding: '14px 24px',
                    borderBottom: '1px solid var(--sl-border)',
                    background: 'var(--sl-bg-1)',
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 16,
                    flexShrink: 0,
                }}
            >
                <span className="sl-label-xs" style={{ color: 'var(--sl-text)' }}>
                    MISSION ARCHIVE
                </span>
                <span style={{ fontSize: 11, color: 'var(--sl-text-dim2)' }}>
                    Completed flights — full telemetry, flight paths, and replays.
                </span>
                <span className="sl-pill dim" style={{ marginLeft: 'auto' }}>
                    {flights.length} flight{flights.length === 1 ? '' : 's'}
                </span>
            </div>

            {/* Body */}
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 24px 56px' }}>
                    {flights.length === 0 ? (
                        <EmptyState status={status} />
                    ) : (
                        <div
                            style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))',
                                gap: 16,
                            }}
                        >
                            {flights.map((f) => (
                                <FlightCard key={`${f.source}-${f.id}`} flight={f} />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function EmptyState({ status }: { status: string }) {
    const msg =
        status === 'disconnected'
            ? 'Supabase is not configured, so only sample flights appear here.'
            : status === 'error'
              ? 'Could not reach the telemetry database. Showing sample flights only.'
              : 'No completed flights yet. Missions appear here once a device lands.';
    return (
        <div
            style={{
                border: '1px solid var(--sl-border)',
                background: 'var(--sl-bg-1)',
                padding: 40,
                textAlign: 'center',
                color: 'var(--sl-text-dim2)',
                fontSize: 12,
            }}
        >
            <div className="sl-label-xs" style={{ marginBottom: 8 }}>
                ARCHIVE EMPTY
            </div>
            {msg}
        </div>
    );
}

function FlightCard({ flight }: { flight: PastFlightSummary }) {
    const name = flight.callsign ?? flight.title ?? flight.deviceId;
    const durationLabel = flight.durationMs !== null ? fmt.duration(flight.durationMs) : '—';
    const launchLabel = flight.launchedAtMs !== null ? fmt.datetime(flight.launchedAtMs) : '—';
    const statusLabel = flight.status?.toUpperCase() ?? '—';

    return (
        <Link
            href={`/dashboard-v2/archive/${encodeURIComponent(flight.id)}`}
            className="sl-dev-card"
            style={{ display: 'block', padding: 0, textDecoration: 'none', overflow: 'hidden' }}
        >
            {/* Header */}
            <div style={{ padding: '16px 18px 12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                        <div
                            style={{
                                fontSize: 16,
                                fontWeight: 500,
                                color: 'var(--sl-ok)',
                                fontFamily: 'var(--sl-mono)',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                            }}
                        >
                            {name}
                        </div>
                        {flight.subtitle && (
                            <div
                                style={{
                                    fontSize: 11,
                                    color: 'var(--sl-text-dim)',
                                    marginTop: 3,
                                    lineHeight: 1.4,
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical',
                                    overflow: 'hidden',
                                }}
                            >
                                {flight.subtitle}
                            </div>
                        )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end', flexShrink: 0 }}>
                        <span className="sl-pill dim">{statusLabel}</span>
                        {flight.source === 'curated' && <span className="sl-pill dim">SAMPLE</span>}
                    </div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--sl-text-dim3)', marginTop: 8, fontFamily: 'var(--sl-mono)' }}>
                    {flight.deviceId} · launched {launchLabel} UTC
                </div>
            </div>

            {/* KPI grid */}
            <div
                style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    borderTop: '1px solid var(--sl-border)',
                }}
            >
                <CardStat label="PEAK ALT" value={fmtAltitudeM(flight.peakAltM)} border="right bottom" />
                <CardStat
                    label="DISTANCE"
                    value={flight.distanceKm !== null ? `${Math.round(flight.distanceKm).toLocaleString()} km` : '—'}
                    border="bottom"
                />
                <CardStat label="DURATION" value={durationLabel} border="right" />
                <CardStat
                    label="PACKETS / FIXES"
                    value={`${flight.rowCount.toLocaleString()} / ${flight.fixCount.toLocaleString()}`}
                />
            </div>

            {/* Footer */}
            <div
                style={{
                    padding: '10px 18px',
                    borderTop: '1px solid var(--sl-border)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: 'var(--sl-bg-1)',
                }}
            >
                <span style={{ fontSize: 10, color: 'var(--sl-text-dim2)' }}>
                    {flight.minTempC !== null ? `min ${flight.minTempC.toFixed(1)}°C` : ''}
                </span>
                <span style={{ fontSize: 11, color: 'var(--sl-ok)', letterSpacing: '0.08em', fontWeight: 500 }}>
                    VIEW REPLAY →
                </span>
            </div>
        </Link>
    );
}

function CardStat({
    label,
    value,
    border = '',
}: {
    label: string;
    value: string;
    border?: string;
}) {
    return (
        <div
            style={{
                padding: '12px 18px',
                borderRight: border.includes('right') ? '1px solid var(--sl-border)' : undefined,
                borderBottom: border.includes('bottom') ? '1px solid var(--sl-border)' : undefined,
            }}
        >
            <div style={{ fontSize: 9, letterSpacing: '0.12em', color: 'var(--sl-text-dim3)', fontWeight: 500 }}>
                {label}
            </div>
            <div
                style={{
                    fontSize: 15,
                    color: 'var(--sl-text-hi)',
                    fontFamily: 'var(--sl-mono)',
                    fontVariantNumeric: 'tabular-nums',
                    marginTop: 4,
                }}
            >
                {value}
            </div>
        </div>
    );
}
