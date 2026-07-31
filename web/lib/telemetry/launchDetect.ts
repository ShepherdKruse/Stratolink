/**
 * Telemetry-derived launch detection.
 *
 * The `devices.launched_at` column is set by hand (or by the activation flow)
 * and can be days off when a payload soaks on the bench before release — the
 * flight clock would show "6d 23h" at the moment of launch. Instead, the
 * dashboard derives the launch moment from the telemetry itself: the flight
 * starts when altitude first climbs decisively above where the packets began.
 *
 * GPS altitude ONLY — deliberately not pressure altitude. Bench prep includes
 * vacuum-chamber runs (observed: 25.6 hPa ≈ 24.9 km "altitude" indoors two
 * days before launch) that are indistinguishable from flight by pressure, but
 * show zero satellites. A real ascent in the open sky has GPS lock. The
 * trade-off: a flight whose GPS never fixes at all won't start the clock —
 * and won't have a map track either, so the clock is the least of it.
 */

export interface LaunchDetectRow {
    /** Epoch ms of the uplink. */
    t: number;
    /** GPS-reported altitude (m MSL), null when the firmware had no fix. */
    alt: number | null;
}

/** Absolute floor for "definitely airborne" (m MSL). */
const MIN_LAUNCH_ALT_M = 300;
/** Required climb above the first GPS fix's altitude (m). Keeps detection
 *  working from elevated launch sites where 300 m MSL is underground. */
const CLIMB_ABOVE_BASELINE_M = 250;

/**
 * Epoch-ms of the detected launch, or null when the balloon is still on the
 * ground (pre-launch bench/soak data only).
 *
 * Rules:
 *  - Baseline = altitude of the first GPS fix in the window.
 *  - If the window already starts airborne (baseline above threshold — e.g.
 *    a landed flight replay whose mission window begins at launch), the first
 *    row is the start.
 *  - Otherwise the launch is the first of two CONSECUTIVE GPS fixes above the
 *    threshold — two so a single corrupt packet can't start the clock.
 *    No-fix rows in between neither confirm nor reset (a GPS dropout
 *    mid-ascent shouldn't restart detection).
 */
export function detectLaunchT(rows: LaunchDetectRow[]): number | null {
    let baseline: number | null = null;
    for (const r of rows) {
        if (r.alt !== null) {
            baseline = r.alt;
            break;
        }
    }
    if (baseline === null) return null;

    if (baseline >= MIN_LAUNCH_ALT_M) return rows[0].t;
    const threshold = Math.max(MIN_LAUNCH_ALT_M, baseline + CLIMB_ABOVE_BASELINE_M);

    let firstAboveT: number | null = null;
    for (const r of rows) {
        if (r.alt === null) continue;
        if (r.alt >= threshold) {
            if (firstAboveT !== null) return firstAboveT;
            firstAboveT = r.t;
        } else {
            firstAboveT = null;
        }
    }
    return null;
}
