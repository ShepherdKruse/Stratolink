import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'Register payload',
    robots: { index: false, follow: false },
};

export default function AdminRegisterLayout({ children }: { children: React.ReactNode }) {
    return children;
}
