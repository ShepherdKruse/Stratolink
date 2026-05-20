import { NextResponse } from 'next/server';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import type { ForecastGpsFix, MonteCarloForecastInput } from '@/lib/wind/forecastTypes';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;
export const runtime = 'nodejs';

type Body = {
    deviceId?: string;
    mission?: string;
    launch?: { lat: number; lon: number; time_utc: string };
    gpsFixes?: ForecastGpsFix[];
    observedTrack?: Array<{ lat: number; lon: number; t: string; alt_m?: number | null }>;
    driftSegment?: Array<[number, number]>;
    baroSamples?: Array<{ time_utc: string; alt_m: number }>;
    pressureHpa?: number;
    forecastHours?: number;
    nEnsemble?: number;
};

function buildInput(body: Body): MonteCarloForecastInput {
    const track = body.observedTrack ?? [];
    if (track.length < 1) throw new Error('observedTrack required');

    const gpsFixes: ForecastGpsFix[] =
        body.gpsFixes ??
        track.map((p) => ({
            lat: p.lat,
            lon: p.lon,
            time_utc: p.t,
            alt_m: p.alt_m ?? undefined,
        }));

    const first = track[0];
    const last = track[track.length - 1];
    const launch = body.launch ?? {
        lat: first.lat,
        lon: first.lon,
        time_utc: first.t,
    };

    return {
        deviceId: body.deviceId ?? 'balloon',
        mission: body.mission,
        launch,
        gpsFixes,
        observedTrackLonLat: track.map((p) => [p.lon, p.lat] as [number, number]),
        driftSegmentLonLat: body.driftSegment,
        baroSamples: body.baroSamples,
        pressureHpa: body.pressureHpa ?? 285,
        forecastHours: body.forecastHours ?? 24,
        nEnsemble: body.nEnsemble,
    };
}

export async function POST(req: Request) {
    try {
        const body = (await req.json()) as Body;
        const forecast = await computeMonteCarloForecast(buildInput(body));
        return NextResponse.json(forecast, {
            headers: { 'Cache-Control': 'private, max-age=300' },
        });
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Forecast compute failed';
        return NextResponse.json({ error: message }, { status: 400 });
    }
}

/** Lightweight GET for quick tests (last fix + pressure only). */
export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const lat = parseFloat(searchParams.get('lat') ?? '');
    const lon = parseFloat(searchParams.get('lon') ?? '');
    const pressureHpa = parseFloat(searchParams.get('pressureHpa') ?? '285');
    const hours = parseInt(searchParams.get('hours') ?? '24', 10);

    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        return NextResponse.json({ error: 'lat and lon required' }, { status: 400 });
    }

    const now = new Date().toISOString();
    const body: Body = {
        deviceId: searchParams.get('device') ?? 'balloon',
        pressureHpa,
        forecastHours: hours,
        observedTrack: [{ lat, lon, t: now }],
        gpsFixes: [{ lat, lon, time_utc: now }],
    };

    try {
        const forecast = await computeMonteCarloForecast(buildInput(body));
        return NextResponse.json(forecast);
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Forecast compute failed';
        return NextResponse.json({ error: message }, { status: 502 });
    }
}
