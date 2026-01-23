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
                        Desktop View
                    </button>
                    <button
                        onClick={() => setActiveView('mobile')}
                        className={`px-6 py-2 rounded-sm border transition-all ${
                            activeView === 'mobile'
                                ? 'border-foreground/20 bg-accent text-foreground'
                                : 'border-border text-muted-foreground hover:border-foreground/10'
                        }`}
                    >
                        Mobile View
                    </button>
                </div>
                )}

                {/* Device Frames */}
                <div
                    className={`mt-12 transition-all duration-1000 delay-300 ${
                        isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
                    }`}
                >
                    <div className={`grid gap-8 ${isMobile ? 'grid-cols-1' : 'lg:grid-cols-2'} items-start`}>
                        {/* Desktop Frame */}
                        <div
                            className={`transition-all duration-500 ${
                                activeView === 'desktop' || isMobile
                                    ? 'opacity-100 scale-100'
                                    : 'opacity-40 scale-95'
                            }`}
                        >
                            <div className="relative">
                                {/* Browser Frame */}
                                <div className="rounded-lg border border-border bg-card shadow-2xl overflow-hidden">
                                    {/* Browser Chrome */}
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

                                    {/* Dashboard Preview */}
                                    <div className="relative bg-[#1a1a1a] aspect-video overflow-hidden">
                                        <iframe
                                            src="/dashboard"
                                            className="w-full h-full border-0 pointer-events-none"
                                            style={{ transform: 'scale(0.5)', transformOrigin: 'top left', width: '200%', height: '200%' }}
                                            title="Desktop Dashboard Preview"
                                        />
                                        {/* Overlay gradient for polish */}
                                        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/20 pointer-events-none" />
                                    </div>
                                </div>

                                {/* Label */}
                                <div className="mt-4 text-center">
                                    <p className="text-sm font-medium text-foreground">Desktop Experience</p>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        3D globe view, detailed telemetry, timeline scrubbing
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Mobile Frame */}
                        <div
                            className={`transition-all duration-500 ${
                                activeView === 'mobile' || isMobile
                                    ? 'opacity-100 scale-100'
                                    : 'opacity-40 scale-95'
                            }`}
                        >
                            <div className="relative flex justify-center">
                                {/* Phone Frame */}
                                <div className="w-[280px] mx-auto">
                                    <div className="relative rounded-[2.5rem] border-8 border-foreground/10 bg-foreground/5 p-2 shadow-2xl">
                                        {/* Notch */}
                                        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-6 bg-foreground/10 rounded-b-2xl z-10" />
                                        
                                        {/* Screen */}
                                        <div className="relative bg-[#1a1a1a] rounded-[1.5rem] overflow-hidden aspect-[9/19.5]">
                                            <iframe
                                                src="/dashboard?preview=mobile"
                                                className="w-full h-full border-0 pointer-events-none"
                                                style={{ transform: 'scale(0.35)', transformOrigin: 'top left', width: '285.7%', height: '285.7%' }}
                                                title="Mobile Dashboard Preview"
                                                sandbox="allow-same-origin allow-scripts"
                                            />
                                            {/* Overlay gradient */}
                                            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-background/20 pointer-events-none" />
                                        </div>

                                        {/* Home Indicator */}
                                        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-foreground/20 rounded-full" />
                                    </div>
                                </div>

                                {/* Label */}
                                <div className="mt-6 text-center">
                                    <p className="text-sm font-medium text-foreground">Mobile Experience</p>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Bottom navigation, swipe gestures, optimized for touch
                                    </p>
                                </div>
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
                            description: 'Live position updates with 3D globe visualization and flight path history.',
                        },
                        {
                            title: 'Telemetry Analysis',
                            description: 'Detailed sensor data with sparkline graphs, health monitoring, and system diagnostics.',
                        },
                        {
                            title: 'Cross-Platform',
                            description: 'Responsive design that adapts seamlessly from desktop workstations to mobile devices.',
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
