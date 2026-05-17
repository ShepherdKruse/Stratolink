import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'Launch kit',
    robots: { index: false, follow: false },
};

export default function LaunchKitLayout({ children }: { children: ReactNode }) {
    return children;
}
