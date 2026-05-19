export type FlightSample = {
    mins: number;
    lat: number | null;
    lon: number | null;
    alt_gps: number | null;
    alt_p: number;
    temp: number;
    pres: number;
    freeze?: 1;
    float?: 1;
};

export type FlightPhase = {
    id: 'asc' | 'frz' | 'flt' | 'drft';
    name: string;
    timeRange: string;
    detail: string;
};

export type FlightReport = {
    slug: string;
    deviceId: string;
    /** Operator callsign — shown as the primary flight name when set. */
    callsign?: string;
    title: string;
    subtitle: string;
    launchedAtUtc: string;
    launchCoords: string;
    comms: string;
    gpsFixes: number;
    kpis: {
        peakAltitudeM: number;
        peakAltitudeFt: number;
        minTempC: number;
        minTempNote: string;
        floatDuration: string;
        floatNote: string;
        groundCoverageKm: number;
        groundCoverageNote: string;
    };
    phases: FlightPhase[];
    chips: { text: string; variant: 'orange' | 'blue' | 'indigo' | 'green' }[];
    footerLine1: string;
    footerLine2: string;
    status: 'complete' | 'in-flight';
    featured?: boolean;
};
