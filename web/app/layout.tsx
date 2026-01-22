import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
    title: 'Stratolink - Pico-Balloon Telemetry System',
    description: 'Global high-altitude balloon tracking system',
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    );
}
