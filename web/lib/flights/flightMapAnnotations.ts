/** Offshore label anchors + leader lines for post-resume GPS updates (Baja Run). */
export type FlightMapAnnotation = {
    point: [number, number];
    label: [number, number];
    utc: string;
    alt: string;
    note: string | null;
    /** Fix dot color on map (default indigo). */
    dotColor?: string;
};

export const BAJA_RUN_GPS_ANNOTATIONS: FlightMapAnnotation[] = [
    {
        point: [-119.002, 33.544],
        label: [-121.35, 34.05],
        utc: '22:56 UTC',
        alt: '9,744 m',
        note: 'GPS resumed',
    },
    {
        point: [-118.391, 32.872],
        label: [-121.1, 33.15],
        utc: '00:29 UTC',
        alt: '9,621 m',
        note: null,
    },
    {
        point: [-117.859, 32.219],
        label: [-120.75, 32.35],
        utc: '01:46 UTC',
        alt: '9,648 m',
        note: null,
    },
    {
        point: [-117.722, 32.013],
        label: [-120.35, 31.55],
        utc: '02:03 UTC',
        alt: '9,682 m',
        note: 'last fix',
    },
];

export const BAJA_RUN_LAUNCH_ANNOTATION: FlightMapAnnotation = {
    point: [-122.426, 37.728],
    label: [-123.55, 38.15],
    utc: '15:55 UTC',
    alt: '734 m · Launch',
    note: null,
    dotColor: '#2d8c55',
};

export const BAJA_RUN_FREEZE_ANNOTATION: FlightMapAnnotation = {
    point: [-121.572, 36.616],
    label: [-122.85, 37.05],
    utc: '18:20 UTC',
    alt: '6,924 m · GPS freeze',
    note: null,
    dotColor: '#c9521f',
};
