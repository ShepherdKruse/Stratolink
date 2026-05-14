import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
    title: 'Claim a callsign',
    description: 'Name your balloon before the launch.',
};

export default function ClaimLayout({ children }: { children: ReactNode }) {
    return children;
}
