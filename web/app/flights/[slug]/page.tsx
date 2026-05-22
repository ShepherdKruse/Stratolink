import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getFlightReport, getFlightReportSlugs } from '@/lib/flights/registry';
import { FlightReportDocument } from '@/components/flights/FlightReportDocument';

type PageProps = {
    params: Promise<{ slug: string }>;
};

export function generateStaticParams() {
    return getFlightReportSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
    const { slug } = await params;
    const report = getFlightReport(slug);
    if (!report) return { title: 'Flight not found' };

    return {
        title: `${report.title} · Flight report`,
        description: `${report.subtitle} — ${report.deviceId}, launched ${report.launchedAtUtc}. Peak altitude ${report.kpis.peakAltitudeM.toLocaleString()} m.`,
        openGraph: {
            title: `${report.title} · Stratolink`,
            description: report.subtitle,
            url: `/flights/${slug}`,
        },
    };
}

export default async function FlightReportPage({ params }: PageProps) {
    const { slug } = await params;
    const report = getFlightReport(slug);

    if (!report) {
        notFound();
    }

    return <FlightReportDocument report={report} />;
}
