import type { ReactNode } from 'react';

const learnFontsUrl =
    'https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Fraunces:opsz,wght@9..144,400;9..144,500&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap';

export default function LearnLayout({ children }: { children: ReactNode }) {
    return (
        <>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
            <link href={learnFontsUrl} rel="stylesheet" />
            {children}
        </>
    );
}
