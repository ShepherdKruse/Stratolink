import { readFileSync } from 'fs';
import { join } from 'path';
import type { Metadata } from 'next';
import { Navigation } from '@/components/navigation';
import { Footer } from '@/components/footer';
import { StratolinkLearnClient } from '@/components/learn/StratolinkLearnClient';
import '@/styles/stratolink-learn.css';

export const metadata: Metadata = {
    title: 'Space within reach',
    description:
        'What is a pico balloon, how Stratolink tracks it through the stratosphere, and what you see on your mission dashboard.',
};

function loadLearnHtml(): string {
    const path = join(process.cwd(), 'content', 'stratolink-learn.html');
    return readFileSync(path, 'utf-8');
}

export default function LearnPage() {
    const contentHtml = loadLearnHtml();

    return (
        <>
            <Navigation />
            <StratolinkLearnClient contentHtml={contentHtml} />
            <Footer />
        </>
    );
}
