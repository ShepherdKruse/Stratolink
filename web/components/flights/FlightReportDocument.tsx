import { readFileSync } from 'fs';
import { join } from 'path';
import Link from 'next/link';
import type { FlightReport } from '@/lib/flights/types';
import '@/styles/baja-run-report.css';

function loadReportHtml(slug: string): string {
    const path = join(process.cwd(), 'content', `${slug}-report.html`);
    return readFileSync(path, 'utf-8');
}

type Props = {
    report: FlightReport;
};

export function FlightReportDocument({ report }: Props) {
    const articleHtml = loadReportHtml(report.slug);

    return (
        <div className="baja-report-page">
            <div className="accentbar" aria-hidden />
            <div className="wrap">
                <nav className="report-breadcrumb" aria-label="Breadcrumb">
                    <Link href="/flights">Flights</Link>
                    <span> / </span>
                    <span>{report.title}</span>
                </nav>
                <article className="paper" dangerouslySetInnerHTML={{ __html: articleHtml }} />
                <nav className="report-links" aria-label="Related pages">
                    <Link href="/flights">All flight reports</Link>
                    <Link href="/docs/flight-path-engine">Flight Path Engine technical note →</Link>
                    <Link href={`/dashboard-v2?device=${encodeURIComponent(report.deviceId)}`}>
                        Live dashboard for {report.deviceId} →
                    </Link>
                </nav>
            </div>
        </div>
    );
}
