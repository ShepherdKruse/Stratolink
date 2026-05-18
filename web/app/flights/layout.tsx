import type { ReactNode } from 'react';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';
import '@/styles/flight-report.css';

export default function FlightsLayout({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen bg-background">
            <Navigation />
            <main>{children}</main>
            <Footer />
        </div>
    );
}
