import type React from 'react';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { Analytics } from '@vercel/analytics/next';
import './globals.css';

const inter = Inter({ subsets: ['latin'], weight: ['300', '400', '500', '600'] });

const siteUrl =
    process.env.NEXT_PUBLIC_SITE_URL?.startsWith('http')
        ? process.env.NEXT_PUBLIC_SITE_URL
        : 'https://stratolink.org';

const ogDescription =
    'High-altitude balloon telemetry and mission control — live tracking, atmospheric data, and ground-station dashboards.';

export const metadata: Metadata = {
    metadataBase: new URL(siteUrl),
    title: {
        default: 'Stratolink · Stratospheric mission telemetry',
        template: '%s · Stratolink',
    },
    description: ogDescription,
    openGraph: {
        title: 'Stratolink',
        description: ogDescription,
        siteName: 'Stratolink',
        locale: 'en_US',
        type: 'website',
        url: '/',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Stratolink',
        description: ogDescription,
    },
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" className="scroll-smooth">
            <body className={`${inter.className} font-sans antialiased`}>
                {children}
                <Analytics />
            </body>
        </html>
    );
}
