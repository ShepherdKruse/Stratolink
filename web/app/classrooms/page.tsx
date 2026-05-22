import { readFileSync } from 'fs';
import { join } from 'path';
import Link from 'next/link';
import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';
import '@/styles/classrooms.css';

export const metadata: Metadata = {
    title: 'For the Classroom',
    description:
        'A STEM proposal for educators — hands-on stratospheric balloon missions with live data, curriculum ties, and a classroom mission kit.',
};

function loadClassroomsHtml(): string {
    const path = join(process.cwd(), 'content', 'stratolink-classrooms.html');
    return readFileSync(path, 'utf-8');
}

export default function ClassroomsPage() {
    const articleHtml = loadClassroomsHtml();

    return (
        <>
            <Navigation />
            <div className="classrooms-page">
                <div className="accentbar" aria-hidden />
                <div className="wrap">
                    <article className="paper" dangerouslySetInnerHTML={{ __html: articleHtml }} />
                    <nav className="classrooms-links" aria-label="Related pages">
                        <Link href="/learn">How the balloon works →</Link>
                        <Link href="/#contact">Contact us about school programs →</Link>
                        <Link href="/docs">Technical documentation →</Link>
                    </nav>
                </div>
            </div>
            <Footer />
        </>
    );
}
