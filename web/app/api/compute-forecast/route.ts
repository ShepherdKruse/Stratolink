import { NextResponse } from 'next/server';
import { buildForecastInputForDevice, listForecastDeviceIds } from '@/lib/wind/buildForecastInput';
import { computeMonteCarloForecast } from '@/lib/wind/monteCarloForecast';
import { isBlobStorageConfigured, storeForecast } from '@/lib/wind/forecastStorage';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;
export const runtime = 'nodejs';

type Result = {
    deviceId: string;
    ok: boolean;
    url?: string;
    error?: string;
    compute_ms?: number;
};

export async function GET(req: Request) {
    const secret = process.env.CRON_SECRET;
    if (!secret) {
        return NextResponse.json(
            { error: 'CRON_SECRET not configured on server' },
            { status: 503 },
        );
    }
    const auth = req.headers.get('authorization');
    if (auth !== `Bearer ${secret}`) {
        return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
    }

    if (!isBlobStorageConfigured()) {
        return NextResponse.json(
            {
                ok: false,
                error: 'BLOB_READ_WRITE_TOKEN not set',
                hint: 'Vercel Dashboard → Storage → Blob → connect to project, then redeploy.',
            },
            { status: 503 },
        );
    }

    const { searchParams } = new URL(req.url);
    const onlyDevice = searchParams.get('device');
    const forecastHours = parseInt(searchParams.get('hours') ?? '24', 10);

    const t0 = Date.now();
    const deviceIds = onlyDevice ? [onlyDevice] : await listForecastDeviceIds();
    const results: Result[] = [];

    for (const deviceId of deviceIds) {
        try {
            const input = await buildForecastInputForDevice(deviceId, forecastHours);
            if (!input) {
                results.push({ deviceId, ok: false, error: 'insufficient telemetry' });
                continue;
            }
            const forecast = await computeMonteCarloForecast(input);
            const url = await storeForecast(deviceId, forecast);
            results.push({
                deviceId,
                ok: true,
                url: url ?? undefined,
                compute_ms: forecast.metadata.compute_ms,
            });
        } catch (e) {
            results.push({
                deviceId,
                ok: false,
                error: e instanceof Error ? e.message : 'compute failed',
            });
        }
    }

    const okCount = results.filter((r) => r.ok).length;

    return NextResponse.json({
        ok: okCount > 0,
        devices: deviceIds.length,
        succeeded: okCount,
        elapsed_ms: Date.now() - t0,
        results,
    });
}
