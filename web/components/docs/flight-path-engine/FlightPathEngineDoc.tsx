'use client';

import { useEffect, useRef } from 'react';
import Script from 'next/script';

const TOC_ITEMS = [
    { id: 'two-questions', n: '1', label: 'Two questions' },
    { id: 'wind', n: '2', label: 'The wind is the engine' },
    { id: 'forecast', n: '3', label: 'Forecasting forward' },
    { id: 'bias', n: '4', label: 'Bias correction' },
    { id: 'ensemble', n: '5', label: 'The Monte Carlo ensemble' },
    { id: 'ellipse', n: '6', label: 'An elliptical uncertainty' },
    { id: 'reconstruct', n: '7', label: 'Reconstructing the past' },
    { id: 'particle', n: '8', label: 'The particle smoother' },
    { id: 'altitude', n: '9', label: 'Altitude as a constraint' },
    { id: 'longgap', n: '10', label: 'Long gaps' },
    { id: 'looping', n: '11', label: 'Letting the path loop' },
    { id: 'honesty', n: '12', label: 'Knowing when to stop' },
    { id: 'serving', n: '13', label: 'Computation and serving' },
    { id: 'limits', n: '14', label: 'Limitations' },
] as const;

declare global {
    interface Window {
        MathJax?: {
            typesetPromise?: (elements?: Element[]) => Promise<void>;
            startup?: { promise: Promise<void> };
        };
    }
}

function typesetMath(root?: HTMLElement | null) {
    const run = () => {
        if (!root || !window.MathJax?.typesetPromise) return;
        void window.MathJax.typesetPromise([root]);
    };
    if (window.MathJax?.typesetPromise) {
        run();
        return;
    }
    const id = window.setInterval(() => {
        if (window.MathJax?.typesetPromise) {
            window.clearInterval(id);
            run();
        }
    }, 80);
    return () => window.clearInterval(id);
}

type Props = {
    articleHtml: string;
};

export function FlightPathEngineDoc({ articleHtml }: Props) {
    const articleRef = useRef<HTMLDivElement>(null);
    const tocRef = useRef<HTMLElement>(null);

    useEffect(() => {
        const root = articleRef.current;
        if (!root) return;
        const cleanupMath = typesetMath(root);

        const links = Array.from(tocRef.current?.querySelectorAll('a') ?? []);
        const byId = new Map<string, HTMLAnchorElement>();
        for (const link of links) {
            const hash = link.getAttribute('href')?.slice(1);
            if (hash) byId.set(hash, link);
        }

        const sections = root.querySelectorAll<HTMLElement>('section[id]');
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (!entry.isIntersecting) continue;
                    links.forEach((l) => l.classList.remove('active'));
                    const active = byId.get(entry.target.id);
                    active?.classList.add('active');
                }
            },
            { rootMargin: '-15% 0px -75% 0px' },
        );
        sections.forEach((s) => observer.observe(s));

        return () => {
            observer.disconnect();
            cleanupMath?.();
        };
    }, [articleHtml]);

    return (
        <>
            <Script id="mathjax-config" strategy="beforeInteractive">
                {`window.MathJax = {
  tex: { inlineMath: [['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] },
  chtml: { scale: 1.0 },
  options: { renderActions: { addMenu: [] } }
};`}
            </Script>
            <Script
                src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
                strategy="afterInteractive"
                onLoad={() => typesetMath(articleRef.current)}
            />

            <div className="fpe-doc min-h-screen pt-20">
                <div className="shell">
                    <nav className="toc" ref={tocRef} aria-label="Table of contents">
                        <div className="toc-title">Contents</div>
                        {TOC_ITEMS.map((item) => (
                            <a key={item.id} href={`#${item.id}`}>
                                <span className="n">{item.n}</span>
                                {item.label}
                            </a>
                        ))}
                    </nav>

                    <div ref={articleRef} dangerouslySetInnerHTML={{ __html: articleHtml }} />
                </div>

                <footer>
                    <div className="footer-inner">
                        Stratolink &middot; Flight Path Engine &middot; Technical Note
                        <br />
                        A working note on how the prediction and reconstruction system operates.
                    </div>
                </footer>
            </div>
        </>
    );
}
