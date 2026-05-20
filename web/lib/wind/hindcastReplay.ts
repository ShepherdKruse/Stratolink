import { computeBias } from './monteCarloForecast';
import { boundsForForecast, fetchWindGrid, snapPressureHpa } from './fetchWindGrid';
import type { ForecastGpsFix } from './forecastTypes';
import { windFieldToGfsGrid } from './gfsGrid';
import { integrateHourlyDriftForward } from './staleGpsExtrapolation';
import { coordAlongPath, haversineKm } from './forecastTimeline';

/** Walk-forward replay horizon (independent of the live forecast hours selector). */
export const HINDCAST_REPLAY_HOURS = 24;

export type HindcastReplayResult = {
    anchor_time_utc: string;
    anchor: { lat: number; lon: number };
    /** Fixes used for bias (only history known at anchor time). */
    n_fixes_used: number;
    bias_correction: {
        speed_factor: number;
        direction_offset_deg: number;
        n_samples: number;
        capped: boolean;
    };
    /** Model nominal path forward from anchor using hourly historical GFS. */
    predicted_path: Array<[number, number]>;
    /** Observed GPS after anchor (ground truth). */
    actual_path: Array<[number, number]>;
    /** Great-circle error at forecast lead times where GPS exists. */
    errors: Array<{ lead_h: number; km: number }>;
};

function obsTimeUtc(t: number): string {
    return new Date(t).toISOString();
}

function positionOnTrack(
    track: Array<{ lat: number; lon: number; t: number }>,
    tMs: number,
): { lat: number; lon: number } | null {
    if (track.length === 0) return null;
    if (tMs <= track[0].t) return { lat: track[0].lat, lon: track[0].lon };
    if (tMs >= track[track.length - 1].t) {
        const last = track[track.length - 1];
        return { lat: last.lat, lon: last.lon };
    }
    for (let i = 1; i < track.length; i++) {
        const a = track[i - 1];
        const b = track[i];
        if (tMs >= a.t && tMs <= b.t) {
            const f = b.t === a.t ? 0 : (tMs - a.t) / (b.t - a.t);
            return {
                lat: a.lat + (b.lat - a.lat) * f,
                lon: a.lon + (b.lon - a.lon) * f,
            };
        }
    }
    return null;
}

function fixesUpToAnchor(
    track: Array<{ lat: number; lon: number; t: number }>,
    anchorMs: number,
): ForecastGpsFix[] {
    return track
        .filter((p) => p.t <= anchorMs + 1000)
        .map((p) => ({
            lat: p.lat,
            lon: p.lon,
            time_utc: obsTimeUtc(p.t),
        }));
}

function actualPathAfter(
    track: Array<{ lat: number; lon: number; t: number }>,
    anchorMs: number,
    horizonH: number,
): Array<[number, number]> {
    const endMs = anchorMs + horizonH * 3_600_000;
    const pts = track.filter((p) => p.t >= anchorMs && p.t <= endMs);
    if (pts.length < 1) return [];
    return pts.map((p) => [p.lon, p.lat] as [number, number]);
}

function errorsAtLeads(
    predicted: Array<[number, number]>,
    actual: Array<[number, number]>,
    anchorMs: number,
    track: Array<{ lat: number; lon: number; t: number }>,
    leads: number[],
): Array<{ lead_h: number; km: number }> {
    const out: Array<{ lead_h: number; km: number }> = [];
    if (predicted.length < 2) return out;

    const pathHours = Math.max(1, predicted.length - 1);
    for (const leadH of leads) {
        const tMs = anchorMs + leadH * 3_600_000;
        const truth = positionOnTrack(track, tMs);
        if (!truth) continue;
        const pred = coordAlongPath(predicted, Math.min(1, leadH / pathHours));
        if (!pred) continue;
        out.push({
            lead_h: leadH,
            km: Math.round(haversineKm(truth.lat, truth.lon, pred[1], pred[0])),
        });
    }
    return out;
}

/**
 * Walk-forward replay: pretend anchor time is "now", use only GPS history up to then,
 * bias-correct from that history, integrate forward with hourly GFS from that date.
 */
export async function hindcastReplayAtAnchor(opts: {
    observedTrack: Array<{ lat: number; lon: number; t: number }>;
    anchorMs: number;
    pressureHpa: number;
    forecastHours?: number;
}): Promise<HindcastReplayResult> {
    const horizonH = opts.forecastHours ?? HINDCAST_REPLAY_HOURS;
    const track = opts.observedTrack;
    if (track.length < 2) throw new Error('Need at least 2 GPS points for hindcast');

    const anchorPos = positionOnTrack(track, opts.anchorMs);
    if (!anchorPos) throw new Error('Anchor time outside track');

    const fixes = fixesUpToAnchor(track, opts.anchorMs);
    if (fixes.length < 2) {
        throw new Error('Need at least 2 GPS fixes before anchor time for bias correction');
    }

    const anchorFix: ForecastGpsFix = {
        lat: anchorPos.lat,
        lon: anchorPos.lon,
        time_utc: obsTimeUtc(opts.anchorMs),
    };

    const levelHpa = snapPressureHpa(opts.pressureHpa);
    const anchorDate = new Date(opts.anchorMs);
    const marginPts = fixes.map((p) => ({ lat: p.lat, lon: p.lon }));
    const gridBounds = boundsForForecast(marginPts, fixes, horizonH);
    const field = await fetchWindGrid(gridBounds, levelHpa, 2.5, anchorDate);
    const gfs = windFieldToGfsGrid(field, 2.5);
    const bias = computeBias(fixes, gfs);

    const predicted_path = await integrateHourlyDriftForward(
        anchorFix,
        levelHpa,
        horizonH,
        bias,
    );
    const actual_path = actualPathAfter(track, opts.anchorMs, horizonH);
    const errors = errorsAtLeads(predicted_path, actual_path, opts.anchorMs, track, [6, 12, 18, 24]);

    return {
        anchor_time_utc: anchorFix.time_utc,
        anchor: { lat: anchorPos.lat, lon: anchorPos.lon },
        n_fixes_used: fixes.length,
        bias_correction: {
            speed_factor: Math.round(bias.speedMult * 100) / 100,
            direction_offset_deg: Math.round(bias.dirOffsetDeg),
            n_samples: bias.nSamples,
            capped: bias.capped,
        },
        predicted_path,
        actual_path,
        errors,
    };
}
