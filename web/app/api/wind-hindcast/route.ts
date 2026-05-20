import { NextResponse } from 'next/server';
import { HINDCAST_REPLAY_HOURS, hindcastReplayAtAnchor } from '@/lib/wind/hindcastReplay';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;
export const runtime = 'nodejs';

type Body = {
    observedTrack?: Array<{ lat: number; lon: number; t: string | number }>;
    anchorMs?: number;
    pressureHpa?: number;
    forecastHours?: number;
};

export async function POST(req: Request) {
    try {
        const body = (await req.json()) as Body;
        const track = (body.observedTrack ?? []).map((p) => ({
            lat: p.lat,
            lon: p.lon,
            t: typeof p.t === 'number' ? p.t : new Date(p.t).getTime(),
        }));
        const anchorMs = body.anchorMs;
        if (!Number.isFinite(anchorMs)) {
            return NextResponse.json({ error: 'anchorMs required' }, { status: 400 });
        }
        if (track.length < 2) {
            return NextResponse.json({ error: 'observedTrack too short' }, { status: 400 });
        }

        const result = await hindcastReplayAtAnchor({
            observedTrack: track,
            anchorMs: anchorMs as number,
            pressureHpa: body.pressureHpa ?? 285,
            forecastHours: body.forecastHours ?? HINDCAST_REPLAY_HOURS,
        });

        return NextResponse.json(result, { headers: { 'Cache-Control': 'no-store' } });
    } catch (e) {
        const message = e instanceof Error ? e.message : 'Hindcast failed';
        return NextResponse.json({ error: message }, { status: 400 });
    }
}
