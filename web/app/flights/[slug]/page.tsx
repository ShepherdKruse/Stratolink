import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getFlightReport, getFlightReportSlugs } from '@/lib/flights/registry';
import { getFlightTelemetry } from '@/lib/flights/getFlightData';
import FlightReportClient from '@/components/flights/FlightReportClient';

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
    const telemetry = getFlightTelemetry(slug);

    if (!report || !telemetry) {
        notFound();
    }

    return <FlightReportClient report={report} telemetry={telemetry} />;
}
