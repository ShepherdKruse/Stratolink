import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import '@/styles/dashboard-v2.css';

const jetbrainsMono = JetBrains_Mono({
    subsets: ['latin'],
    weight: ['400', '500', '600'],
    variable: '--font-jetbrains-mono',
    display: 'swap',
});

export const metadata: Metadata = {
    title: 'Stratolink — Mission Control v2',
    description: 'Redesigned dashboard reading live telemetry from Supabase.',
};

export default function DashboardV2Layout({ children }: { children: React.ReactNode }) {
    return <div className={jetbrainsMono.variable}>{children}</div>;
}
