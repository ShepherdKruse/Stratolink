import type { FlightReport } from './types';

export const FLIGHT_REPORTS: FlightReport[] = [
    {
        slug: 'baja-run',
        deviceId: 'stratolink-3',
        callsign: 'stratolink-3',
        title: 'The Baja Run',
        subtitle: 'San Francisco Bay to Baja, dark for a day and a half, then back north to New Mexico',
        launchedAtUtc: '17 May 2026, 15:55 UTC',
        launchCoords: '37.728°N, 122.426°W',
        comms: 'Satellite IoT over LoRa',
        gpsFixes: 103,
        status: 'complete',
        featured: true,
        kpis: {
            peakAltitudeM: 9814,
            peakAltitudeFt: 32198,
            minTempC: -38.2,
            minTempNote: 'During the overnight blackout',
            floatDuration: '54.6',
            floatNote: 'Launch to final fix',
            groundCoverageKm: 2000,
            groundCoverageNote: 'Across the confirmed track',
        },
        phases: [],
        chips: [],
        footerLine1: 'stratolink · the baja run · compiled may 2026',
        footerLine2: 'stratolink-3 · 103 gps fixes · satellite iot over lora',
    },
];

export function getFlightReport(slug: string): FlightReport | undefined {
    return FLIGHT_REPORTS.find((f) => f.slug === slug);
}

export function getFlightReportSlugs(): string[] {
    return FLIGHT_REPORTS.map((f) => f.slug);
}
