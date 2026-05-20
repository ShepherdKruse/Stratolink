import { readFileSync } from 'fs';
import { join } from 'path';
import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';
import { FlightPathEngineDoc } from '@/components/docs/flight-path-engine/FlightPathEngineDoc';
import '@/styles/flight-path-engine.css';

export const metadata: Metadata = {
    title: 'Flight Path Engine',
    description:
        'Technical note on Stratolink forecasting, particle reconstruction, and occupancy footprints for under-determined gaps.',
};

function loadArticleHtml(): string {
    const path = join(process.cwd(), 'content', 'flight-path-engine-article.html');
    return readFileSync(path, 'utf-8');
}

export default function FlightPathEnginePage() {
    const articleHtml = loadArticleHtml();

    return (
        <>
            <Navigation />
            <FlightPathEngineDoc articleHtml={articleHtml} />
            <Footer />
        </>
    );
}
