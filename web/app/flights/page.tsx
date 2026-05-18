import type { Metadata } from 'next';
import { FLIGHT_REPORTS } from '@/lib/flights/registry';
import FlightsIndex from '@/components/flights/FlightsIndex';

export const metadata: Metadata = {
    title: 'Prior flights',
    description:
        'Stratolink balloon flight reports — post-mission summaries with altitude profiles, telemetry, and flight paths.',
    openGraph: {
        title: 'Prior flights · Stratolink',
        description: 'Post-flight summaries from Stratolink pico balloon missions.',
        url: '/flights',
    },
};

export default function FlightsPage() {
    const flights = [...FLIGHT_REPORTS].sort((a, b) => {
        if (a.featured && !b.featured) return -1;
        if (!a.featured && b.featured) return 1;
        return 0;
    });

    return <FlightsIndex flights={flights} />;
}
