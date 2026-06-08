'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

export function DashboardShowcase() {
    const [isVisible, setIsVisible] = useState(false);
    const [activeView, setActiveView] = useState<'desktop' | 'mobile'>('desktop');
    const [isMobile, setIsMobile] = useState(false);
    const sectionRef = useRef<HTMLElement>(null);

    useEffect(() => {
        const checkMobile = () => setIsMobile(window.innerWidth < 640);
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);

    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setIsVisible(true);
                }
            },
            { threshold: 0.2 },
        );

        if (sectionRef.current) {
            observer.observe(sectionRef.current);
        }

        return () => observer.disconnect();
    }, []);

    return (
        <section
            ref={sectionRef}
            id="dashboard"
            className="border-b bg-background py-24 sm:py-32"
        >
            <div className="mx-auto max-w-7xl px-6 sm:px-8">
                {/* Header */}
                <div
                    className={`mx-auto max-w-2xl text-center transition-all duration-1000 ${
                        isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                    }`}
                >
                    <h2 className="text-3xl font-light tracking-tight text-foreground sm:text-4xl">
                        Mission Control Dashboard
                    </h2>
                    <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
                        Real-time tracking, telemetry visualization, and fleet management in a unified interface.
                        Access your balloon network from any device with responsive design optimized for desktop and mobile.
                    </p>
                    <p className="mt-4 text-sm text-muted-foreground">
                        After a mission ends, read the full post-flight report in{' '}
                        <Link href="/flights" className="underline underline-offset-2 hover:text-foreground">
                            Prior flights
                        </Link>
                        .
                    </p>
                </div>

                {/* View Toggle - Desktop Only */}
                {!isMobile && (
                <div className="mt-12 flex items-center justify-center gap-4">
                    <button
                        onClick={() => setActiveView('desktop')}
                        className={`px-6 py-2 rounded-sm border transition-all ${
                            activeView === 'desktop'
                                ? 'border-foreground/20 bg-accent text-foreground'
                                : 'border-border text-muted-foreground hover:border-foreground/10'
                        }`}
                    >
                        Desktop view
                    </button>
                    <button
                        onClick={() => setActiveView('mobile')}
                        className={`px-6 py-2 rounded-sm border transition-all ${
                            activeView === 'mobile'
                                ? 'border-foreground/20 bg-accent text-foreground'
                                : 'border-border text-muted-foreground hover:border-foreground/10'
                        }`}
                    >
                        Mobile view
                    </button>
                </div>
                )}

                {/* Device Frames */}
                <div
                    className={`mt-12 transition-all duration-1000 delay-300 ${
                        isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                    }`}
                >
                    <div className={`grid gap-12 ${isMobile ? 'grid-cols-1' : 'lg:grid-cols-2'} items-start`}>
                        {/* Desktop Frame — hidden on mobile, where it's unreadable anyway */}
                        {!isMobile && (
                            <div
                                className={`transition-all duration-500 ${
                                    activeView === 'desktop'
                                        ? 'opacity-100 scale-100'
                                        : 'opacity-40 scale-95'
                                }`}
                            >
                                <div className="rounded-lg border border-border bg-card shadow-2xl overflow-hidden">
                                    <div className="bg-muted/50 border-b border-border px-4 py-3 flex items-center gap-2">
                                        <div className="flex gap-1.5">
                                            <div className="w-3 h-3 rounded-full bg-red-500/20" />
                                            <div className="w-3 h-3 rounded-full bg-yellow-500/20" />
                                            <div className="w-3 h-3 rounded-full bg-green-500/20" />
                                        </div>
                                        <div className="flex-1 mx-4">
                                            <div className="bg-background border border-border rounded px-3 py-1.5 text-xs text-muted-foreground text-center">
                                                stratolink.org/dashboard
                                            </div>
                                        </div>
                                    </div>
                                    <div className="relative bg-[#1a1a1a] aspect-video overflow-hidden">
                                        <iframe
                                            src="/dashboard"
                                            className="w-full h-full border-0 pointer-events-none"
                                            style={{ transform: 'scale(0.5)', transformOrigin: 'top left', width: '200%', height: '200%' }}
                                            title="Mission Control desktop preview"
                                        />
                                        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/20 pointer-events-none" />
                                    </div>
                                </div>

                                <div className="mt-4 text-center">
                                    <p className="text-sm font-medium text-foreground">Desktop · Mission Control</p>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Fleet roster, Mapbox track, KPIs · live Supabase telemetry
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* Mobile Phone Frame — always shown */}
                        <div
                            className={`flex flex-col items-center transition-all duration-500 ${
                                activeView === 'mobile' || isMobile
                                    ? 'opacity-100 scale-100'
                                    : 'opacity-40 scale-95'
                            }`}
                        >
                            <div className={isMobile ? 'w-[260px]' : 'w-[280px]'}>
                                <div className="relative rounded-[2.5rem] border-8 border-foreground/10 bg-foreground/5 p-2 shadow-2xl">
                                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-6 bg-foreground/10 rounded-b-2xl z-10" />
                                    <div className="relative bg-[#1a1a1a] rounded-[1.5rem] overflow-hidden aspect-[9/19.5]">
                                        <iframe
                                            src="/dashboard?preview=mobile"
                                            className="w-full h-full border-0 pointer-events-none"
                                            title="Mission Control mobile preview"
                                            sandbox="allow-same-origin allow-scripts"
                                        />
                                        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/20 pointer-events-none" />
                                    </div>
                                    <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-foreground/20 rounded-full" />
                                </div>
                            </div>

                            <div className="mt-6 text-center">
                                <p className="text-sm font-medium text-foreground">Mobile · Mission Control</p>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Same fleet, optimized for phones · Fleet, Map, Telemetry, Alerts
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Features Grid */}
                <div
                    className={`mt-16 grid gap-6 sm:grid-cols-3 transition-all duration-1000 delay-500 ${
                        isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                    }`}
                >
                    {[
                        {
                            title: 'Real-Time Tracking',
                            description:
                                'Mapbox-backed fleet map, per-device trails, GPS validity, and instant selection from Supabase-backed telemetry.',
                        },
                        {
                            title: 'Telemetry Analysis',
                            description:
                                'Device Tracker scrub sync, Telemetry Lab dual-axis stacks, anomalies, packet inspector.',
                        },
                        {
                            title: 'Cross-Platform',
                            description:
                                'Responsive dashboards with dedicated Mission Control, Device Tracker, and Lab routes.',
                        },
                    ].map((feature, index) => (
                        <div
                            key={feature.title}
                            className="rounded-sm border border-border bg-card p-6 shadow-sm"
                            style={{ transitionDelay: `${500 + index * 100}ms` }}
                        >
                            <h3 className="text-lg font-normal text-foreground">{feature.title}</h3>
                            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                                {feature.description}
                            </p>
                        </div>
                    ))}
                </div>

                {/* CTA */}
                <div
                    className={`mt-12 text-center transition-all duration-1000 delay-700 ${
                        isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                    }`}
                >
                    <Link
                        href="/dashboard"
                        className="inline-flex items-center gap-2 rounded-sm border border-foreground/20 bg-foreground px-6 py-3 text-sm font-medium text-background transition-all hover:bg-foreground/90 hover:border-foreground/30"
                    >
                        Open Dashboard
                        <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 5l7 7-7 7"
                            />
                        </svg>
                    </Link>
                </div>
            </div>
        </section>
    );
}
