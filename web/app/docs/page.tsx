import type { ReactNode } from 'react';
import Link from 'next/link';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';

type DocCard = {
    title: string;
    description: string;
    href: string;
    icon: ReactNode;
};

const featuredLearn: DocCard = {
    title: 'Pico Balloons',
    description:
        'Illustrated guide — what a pico balloon is, how it flies, and how Stratolink tracks it live.',
    href: '/learn',
    icon: (
        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
            />
        </svg>
    ),
};

const featuredClassrooms: DocCard = {
    title: 'For the Classroom',
    description:
        'STEM proposal for teachers — what students do, curriculum ties, safety, and the classroom mission kit.',
    href: '/classrooms',
    icon: (
        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 14l9-5-9-5-9 5 9 5zm0 0v6m-6-3l6 3 6-3"
            />
        </svg>
    ),
};

function FeaturedDocCard({ card, label }: { card: DocCard; label: string }) {
    return (
        <Link
            href={card.href}
            className="group flex min-w-0 flex-col gap-6 rounded-sm border border-border bg-card p-6 shadow-sm transition-all duration-300 hover:border-foreground/20 hover:shadow-md sm:flex-row sm:items-center sm:gap-10 sm:p-8"
        >
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-sm bg-accent text-foreground">
                {card.icon}
            </div>
            <div className="min-w-0 flex-1">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
                <p className="mt-2 text-2xl font-light tracking-tight text-foreground sm:text-3xl">{card.title}</p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground sm:text-base">{card.description}</p>
            </div>
            <span className="inline-flex shrink-0 items-center text-sm font-medium text-foreground/60 group-hover:text-foreground">
                Read more
                <svg
                    className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
            </span>
        </Link>
    );
}

const guideCards: DocCard[] = [
    {
        title: 'Getting Started',
        description: 'Set up your Stratolink system from scratch',
        href: '/docs/getting-started',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
        ),
    },
    {
        title: 'Dashboard Guide',
        description: 'Navigate Mission Control and track your fleet',
        href: '/docs/dashboard',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
            </svg>
        ),
    },
    {
        title: 'Hardware Setup',
        description: 'Configure your RAK3172 hardware and firmware',
        href: '/docs/hardware',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
                />
            </svg>
        ),
    },
    {
        title: 'API Reference',
        description: 'Integrate with Stratolink APIs and webhooks',
        href: '/docs/api',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
        ),
    },
    {
        title: 'Troubleshooting',
        description: 'Common issues and solutions',
        href: '/docs/troubleshooting',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
            </svg>
        ),
    },
];

const technicalCards: DocCard[] = [
    {
        title: 'Flight Path Engine',
        description: 'Forecasting, particle reconstruction, and occupancy footprints for long GPS gaps',
        href: '/docs/flight-path-engine',
        icon: (
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
                />
            </svg>
        ),
    },
];

function DocCardLink({ card }: { card: DocCard }) {
    return (
        <Link
            href={card.href}
            className="group flex min-h-full min-w-0 flex-col rounded-sm border border-border bg-card p-6 shadow-sm transition-all duration-300 hover:border-foreground/20 hover:shadow-md sm:p-7"
        >
            <div className="text-muted-foreground transition-colors group-hover:text-foreground">{card.icon}</div>
            <p className="mt-5 text-lg font-medium leading-snug text-foreground [overflow-wrap:anywhere]">
                {card.title}
            </p>
            <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{card.description}</p>
            <span className="mt-5 inline-flex items-center text-sm font-medium text-foreground/60 group-hover:text-foreground">
                Read more
                <svg
                    className="ml-2 h-4 w-4 shrink-0 transition-transform group-hover:translate-x-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
            </span>
        </Link>
    );
}

function DocSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section>
            <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</h2>
            <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
        </section>
    );
}

export default function DocsPage() {
    return (
        <div className="min-h-screen bg-background">
            <Navigation />
            <main>
                <div className="border-b bg-background">
                    <div className="mx-auto max-w-6xl px-6 py-16 sm:px-8 sm:py-20">
                        <h1 className="text-4xl font-light tracking-tight text-foreground sm:text-5xl">Documentation</h1>
                        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted-foreground">
                            Guides for launching, operating, and integrating with Stratolink — plus the science behind
                            flight tracking.
                        </p>
                    </div>
                </div>

                <div className="mx-auto max-w-6xl space-y-14 px-6 py-14 sm:px-8 sm:py-20">
                    <div className="grid gap-5 lg:grid-cols-2">
                        <FeaturedDocCard card={featuredLearn} label="Start here" />
                        <FeaturedDocCard card={featuredClassrooms} label="For educators" />
                    </div>

                    <DocSection title="Guides">
                        {guideCards.map((card) => (
                            <DocCardLink key={card.href} card={card} />
                        ))}
                    </DocSection>

                    <DocSection title="Technical">
                        {technicalCards.map((card) => (
                            <DocCardLink key={card.href} card={card} />
                        ))}
                    </DocSection>

                    <div className="rounded-sm border border-border bg-card p-6 sm:p-8">
                        <h2 className="text-xl font-light text-foreground">Quick links</h2>
                        <div className="mt-5 grid gap-3 sm:grid-cols-2">
                            <Link
                                href="https://github.com/ShepherdKruse/Stratolink"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex min-w-0 items-center gap-3 rounded-sm px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                            >
                                <svg className="h-5 w-5 shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
                                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                                </svg>
                                <span className="[overflow-wrap:anywhere]">GitHub Repository</span>
                            </Link>
                            <Link
                                href="/dashboard-v2"
                                className="flex min-w-0 items-center gap-3 rounded-sm px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                            >
                                <svg className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                                    />
                                </svg>
                                Mission Control Dashboard
                            </Link>
                            <Link
                                href="/#contact"
                                className="flex min-w-0 items-center gap-3 rounded-sm px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                            >
                                <svg className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                                    />
                                </svg>
                                Contact Support
                            </Link>
                            <Link
                                href="/#partnerships"
                                className="flex min-w-0 items-center gap-3 rounded-sm px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                            >
                                <svg className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                                    />
                                </svg>
                                Partnerships
                            </Link>
                        </div>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}
