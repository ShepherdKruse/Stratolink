/**
 * Client-side balloon-path integrator — a faithful JS port of balloon_sim's
 * Euler advection (stratolink-simulation/balloon_sim/trajectory.py), now over a
 * TIME SERIES of 300 hPa wind fields so paths evolve as real winds do.
 *
 * At each step it samples the wind (u, v) at the balloon's position AND the
 * current simulation time (bilinear in space, linear in time between daily
 * frames), then advects with the wind. Because the wind changes through the
 * flight — and because each launch starts at a different time in the series —
 * launching from the same spot at different moments yields different paths,
 * exactly like the real atmosphere.
 *
 * The field is /wind_300hpa_series.{json,bin}: NCEP Reanalysis-2 300 hPa,
 * 2.5° grid, ~30 daily frames, Int16-scaled to keep the payload small.
 * Longitudes stay continuous so the rendered line never tears.
 */

export type LngLat = [number, number];

export interface WindSeries {
    nlat: number;
    nlon: number;
    lat0: number; // latitude of row 0 (ascending)
    lon0: number; // longitude of col 0 (0°, ascending, 0..360)
    dlat: number;
    dlon: number;
    nframes: number;
    frameHours: number; // hours between frames
    scale: number; // stored = m/s * scale
    u: Int16Array; // [frame][lat][lon] row-major, all frames
    v: Int16Array;
}

const KM_PER_DEG_LAT = 111.111;
const MS_TO_KMH = 3.6;

/** Fetch the header + Int16 binary and assemble a WindSeries. */
export async function loadWindSeries(headerUrl: string): Promise<WindSeries> {
    const hdr = await (await fetch(headerUrl)).json();
    const binUrl = headerUrl.replace(/[^/]+$/, hdr.bin);
    const buf = await (await fetch(binUrl)).arrayBuffer();
    const all = new Int16Array(buf);
    const per = hdr.nframes * hdr.nlat * hdr.nlon;
    return {
        nlat: hdr.nlat, nlon: hdr.nlon, lat0: hdr.lat0, lon0: hdr.lon0,
        dlat: hdr.dlat, dlon: hdr.dlon, nframes: hdr.nframes,
        frameHours: hdr.frameHours, scale: hdr.scale,
        u: all.subarray(0, per),
        v: all.subarray(per, per * 2),
    };
}

/** Bilinear-sample one frame's wind (m/s). Longitude wraps; latitude clamps. */
function sampleFrame(w: WindSeries, frame: number, lat: number, lon: number): { u: number; v: number } {
    const clampedLat = Math.max(-90, Math.min(90, lat));
    const fi = (clampedLat - w.lat0) / w.dlat;
    const i0 = Math.max(0, Math.min(w.nlat - 1, Math.floor(fi)));
    const i1 = Math.min(w.nlat - 1, i0 + 1);
    const ti = fi - i0;

    const lonWrapped = ((lon % 360) + 360) % 360;
    const fj = (lonWrapped - w.lon0) / w.dlon;
    const j0 = ((Math.floor(fj) % w.nlon) + w.nlon) % w.nlon;
    const j1 = (j0 + 1) % w.nlon;
    const tj = fj - Math.floor(fj);

    const base = frame * w.nlat * w.nlon;
    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
    const bilerp = (arr: Int16Array) =>
        lerp(
            lerp(arr[base + i0 * w.nlon + j0], arr[base + i0 * w.nlon + j1], tj),
            lerp(arr[base + i1 * w.nlon + j0], arr[base + i1 * w.nlon + j1], tj),
            ti,
        ) / w.scale;

    return { u: bilerp(w.u), v: bilerp(w.v) };
}

/** Sample wind at a fractional frame index (linear time interpolation). */
function sampleWind(w: WindSeries, lat: number, lon: number, frameFloat: number): { u: number; v: number } {
    const f0 = Math.max(0, Math.min(w.nframes - 1, Math.floor(frameFloat)));
    const f1 = Math.min(w.nframes - 1, f0 + 1);
    const tf = frameFloat - f0;
    const a = sampleFrame(w, f0, lat, lon);
    if (tf === 0 || f0 === f1) return a;
    const b = sampleFrame(w, f1, lat, lon);
    return { u: a.u + (b.u - a.u) * tf, v: a.v + (b.v - a.v) * tf };
}

export interface SimulateOptions {
    /** Hours per step (default 1). */
    dtHours?: number;
    /** Number of steps (default 360 ≈ 15 days at 1h). */
    steps?: number;
    /** Simulation hour the launch begins at, into the wind series (default 0).
     *  Different start hours → different (and differently-evolving) winds. */
    startHour?: number;
}

/** Total span of the wind series, in hours. */
export function seriesSpanHours(w: WindSeries): number {
    return (w.nframes - 1) * w.frameHours;
}

/**
 * Integrate a balloon path from a launch point and start time. Returns
 * continuous-longitude [lon, lat] points (lon may run past ±180).
 */
export function simulatePath(
    w: WindSeries,
    startLon: number,
    startLat: number,
    opts: SimulateOptions = {},
): LngLat[] {
    const dt = opts.dtHours ?? 1;
    const steps = opts.steps ?? 360;
    const startHour = opts.startHour ?? 0;

    let lat = startLat;
    let lon = startLon; // kept continuous
    const path: LngLat[] = [[lon, lat]];

    for (let n = 0; n < steps; n++) {
        const frameFloat = (startHour + n * dt) / w.frameHours;
        const { u, v } = sampleWind(w, lat, lon, frameFloat);
        const uKmh = u * MS_TO_KMH;
        const vKmh = v * MS_TO_KMH;

        const cosLat = Math.cos((lat * Math.PI) / 180);
        const dLat = (vKmh * dt) / KM_PER_DEG_LAT;
        const dLon = (uKmh * dt) / (KM_PER_DEG_LAT * Math.max(0.05, Math.abs(cosLat)));

        lat += dLat;
        lon += dLon;

        // Pole reflection (mirror lat, flip longitude by 180) — matches the sim.
        if (lat > 90) { lat = 180 - lat; lon += 180; }
        else if (lat < -90) { lat = -180 - lat; lon += 180; }

        path.push([lon, lat]);
    }
    return path;
}
