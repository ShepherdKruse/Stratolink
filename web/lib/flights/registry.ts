import type { FlightReport } from './types';

export const FLIGHT_REPORTS: FlightReport[] = [
    {
        slug: 'baja-run',
        deviceId: 'stratolink-3',
        callsign: 'stratolink-3',
        title: 'The Baja Run',
        subtitle: 'San Francisco Bay to Baja California',
        launchedAtUtc: '17 May 2026, 15:55 UTC',
        launchCoords: '37.728°N, 122.426°W',
        comms: 'LoRa / Satellite IoT',
        gpsFixes: 101,
        status: 'complete',
        featured: true,
        kpis: {
            peakAltitudeM: 9744,
            peakAltitudeFt: 31967,
            minTempC: -38.2,
            minTempNote: 'Late float phase',
            floatDuration: '~10',
            floatNote: 'Stable 284–287 hPa',
            groundCoverageKm: 900,
            groundCoverageNote: 'SF Bay to near Tijuana',
        },
        phases: [
            {
                id: 'asc',
                name: 'Ascent',
                timeRange: '15:55 → 18:20 UTC',
                detail: '0.70 m/s avg · 734 → 6,924 m GPS',
            },
            {
                id: 'frz',
                name: 'GPS Freeze',
                timeRange: '18:20 → 19:26 UTC',
                detail: 'Pressure tracked rise to ~9,479 m',
            },
            {
                id: 'flt',
                name: 'Float ~9,500 m',
                timeRange: '19:26 → 22:56 UTC',
                detail: 'Stable 284–287 hPa',
            },
            {
                id: 'drft',
                name: 'Drift & Track',
                timeRange: '22:56 → +02:58 UTC',
                detail: 'GPS resumed · 9,744 m · 4 unique positions',
            },
        ],
        chips: [
            { text: 'Launch · T+0 · 734 m · 37.73°N 122.43°W', variant: 'blue' },
            { text: 'Avg ascent 0.70 m/s · within target 0.5–1.0 m/s', variant: 'blue' },
            {
                text: 'GPS freeze · T+145 min · locked at 6,924 m · under 3 satellites',
                variant: 'orange',
            },
            {
                text: 'Float confirmed · T+211 min · 285.7 hPa · 9,491 m barometric',
                variant: 'indigo',
            },
            {
                text: 'GPS resumed · T+421 min · 9,744 m · San Nicolas Island area · position then stale across repeated readings',
                variant: 'indigo',
            },
            { text: 'Last fix · 32.01°N 117.72°W · near Tijuana / San Diego border', variant: 'green' },
        ],
        footerLine1: 'stratolink · the baja run · compiled may 2026',
        footerLine2: 'stratolink-3 · 101 gps fixes · lora / satellite iot',
    },
];

export function getFlightReport(slug: string): FlightReport | undefined {
    return FLIGHT_REPORTS.find((f) => f.slug === slug);
}

export function getFlightReportSlugs(): string[] {
    return FLIGHT_REPORTS.map((f) => f.slug);
}
