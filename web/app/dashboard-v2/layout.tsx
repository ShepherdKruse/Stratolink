import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import '@/styles/dashboard-v2.css';

/* Monospace drives the entire interface — labels, headings, data — for a
 * precise technical-instrument character. */
const jetbrainsMono = JetBrains_Mono({
    subsets: ['latin'],
    weight: ['400', '500', '600', '700'],
    variable: '--font-jetbrains-mono',
    display: 'swap',
});

export const metadata: Metadata = {
    title: 'Mission Control',
    description: 'Fleet overview and live telemetry from Supabase (dashboard v2).',
    openGraph: {
        title: 'Mission Control · Stratolink',
        description: 'Fleet overview and live telemetry — dashboard v2.',
    },
};

export default function DashboardV2Layout({ children }: { children: React.ReactNode }) {
    return <div className={jetbrainsMono.variable}>{children}</div>;
}
