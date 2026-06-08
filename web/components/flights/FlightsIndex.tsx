'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { FlightReport } from '@/lib/flights/types';

type FlightsIndexProps = {
    flights: FlightReport[];
};

export default function FlightsIndex({ flights }: FlightsIndexProps) {
    return (
        <div className="flights-index mx-auto max-w-5xl px-6 py-16 sm:px-8 sm:py-24">
            <div className="mx-auto max-w-2xl text-center">
                <p className="text-xs font-medium uppercase tracking-widest text-[#c9521f]">
                    Flight archive
                </p>
                <h1 className="mt-3 text-4xl font-light tracking-tight text-foreground sm:text-5xl">
                    Prior flights
                </h1>
                <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                    Post-flight summaries with altitude profiles, telemetry traces, and mission timelines.
                    Live tracking is in{' '}
                    <Link href="/dashboard" className="underline underline-offset-2 hover:text-foreground">
                        Mission Control
                    </Link>
                    .
                </p>
            </div>

            <ul className="mt-14 grid gap-5 sm:grid-cols-1">
                {flights.map((flight) => (
                    <li key={flight.slug}>
                        <Link
                            href={`/flights/${flight.slug}`}
                            className="flight-card group block rounded-lg border bg-card p-6 sm:p-8"
                        >
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                <div>
                                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                                        {flight.deviceId} ·{' '}
                                        {flight.status === 'complete' ? 'Complete' : 'In flight'}
                                    </p>
                                    <h2 className="mt-2 text-2xl font-light text-foreground group-hover:text-[#c9521f] transition-colors">
                                        {flight.title}
                                    </h2>
                                    <p className="mt-1 text-muted-foreground">{flight.subtitle}</p>
                                    <p className="mt-3 text-sm text-muted-foreground">
                                        Launched {flight.launchedAtUtc} · Peak{' '}
                                        {flight.kpis.peakAltitudeM.toLocaleString()} m · ~
                                        {flight.kpis.groundCoverageKm.toLocaleString()} km ·{' '}
                                        {flight.kpis.floatDuration} hrs tracked
                                    </p>
                                </div>
                                <span className="inline-flex items-center gap-1 text-sm font-medium text-[#c9521f] shrink-0">
                                    Read report
                                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                                </span>
                            </div>
                        </Link>
                    </li>
                ))}
            </ul>

            {flights.length === 0 && (
                <p className="mt-12 text-center text-muted-foreground">No flight reports published yet.</p>
            )}
        </div>
    );
}
