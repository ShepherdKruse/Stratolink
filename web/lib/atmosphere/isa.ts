/**
 * U.S. Standard Atmosphere 1976 (USSA-1976), valid 0–32 km.
 *
 * Three-layer model (troposphere, tropopause, lower stratosphere) ported
 * from `simulation/predictor/atmosphere/isa.py` so the dashboard can derive
 * altitude from a barometric reading without round-tripping through the
 * Python predictor service. The two implementations share an authoritative
 * reference (NASA TM-X-74335) and produce values within < 0.1 % of each
 * other at every altitude in the supported range — the predictor's pytest
 * suite acts as the ground truth for either.
 *
 * Rationale: the firmware's MS5611 barometer reports a fresh pressure on
 * every uplink, so a pressure-derived altitude is updated even when the
 * MAX-M10S GPS has lost lock. We saw exactly this on the stratolink-3
 * launch (May 2026): GPS got stuck on a stale cached fix at 6924 m while
 * pressure-altitude correctly tracked the balloon up through 10 km. The
 * dashboard surfaces both so the operator can spot this divergence and
 * trust the pressure value when GPS goes silent.
 *
 * Why not refine with the measured payload temperature? The TMP117 reads
 * PCB temperature, which is dominated by direct solar gain (typically
 * −10 to +30 °C in flight) and is *not* a useful proxy for atmospheric
 * column temperature. ISA's standard temperature profile gives much
 * better results in practice. We intentionally don't accept temperature
 * as an input to keep the abstraction honest.
 */

/* Sea-level reference conditions (USSA-1976 Table 1). */
const T0_K = 288.15;
const P0_PA = 101325.0;

/* Physical constants. */
const G0_M_S2 = 9.80665;       /* standard gravity */
const R_AIR_J_KG_K = 287.0528; /* specific gas constant for dry air */

/* Supported altitude range. Outside this we refuse to extrapolate — the
 * 32 km bound is well above pico-balloon float altitude (~12–14 km) so
 * this should never bite during normal operation. */
const H_MIN_M = 0.0;
const H_MAX_M = 32000.0;

interface Layer {
    h_base_m: number;       /* altitude at base of layer */
    T_base_K: number;       /* temperature at base of layer */
    P_base_Pa: number;      /* pressure at base of layer */
    lapse_K_per_m: number;  /* dT/dh in this layer; 0 for isothermal */
}

/* Build the three-layer USSA-1976 table for 0–32 km. Each layer's base
 * pressure is integrated from the previous layer's exit conditions so the
 * table is self-consistent — no risk of a seam discontinuity at 11 km
 * (tropopause) or 20 km. */
function buildLayers(): Layer[] {
    const layers: Layer[] = [
        { h_base_m: 0.0, T_base_K: T0_K, P_base_Pa: P0_PA, lapse_K_per_m: -0.0065 },
    ];
    const transitions: Array<[number, number]> = [
        [11000.0, 0.0],       /* tropopause: isothermal at 216.65 K */
        [20000.0, 0.001],     /* lower stratosphere: +1 K/km */
    ];
    for (const [h_top, next_lapse] of transitions) {
        const prev = layers[layers.length - 1];
        const T_top = prev.T_base_K + prev.lapse_K_per_m * (h_top - prev.h_base_m);
        let P_top: number;
        if (prev.lapse_K_per_m === 0.0) {
            P_top = prev.P_base_Pa * Math.exp(
                -G0_M_S2 * (h_top - prev.h_base_m) / (R_AIR_J_KG_K * prev.T_base_K)
            );
        } else {
            P_top = prev.P_base_Pa * Math.pow(
                T_top / prev.T_base_K,
                -G0_M_S2 / (R_AIR_J_KG_K * prev.lapse_K_per_m)
            );
        }
        layers.push({
            h_base_m: h_top,
            T_base_K: T_top,
            P_base_Pa: P_top,
            lapse_K_per_m: next_lapse,
        });
    }
    return layers;
}

const LAYERS: ReadonlyArray<Layer> = buildLayers();

/**
 * Altitude (m above mean sea level) for a given barometric pressure (hPa).
 *
 * Returns `null` if the pressure is outside the USSA-1976 0–32 km range,
 * not finite, or null itself — callers can treat that uniformly as "no
 * pressure-altitude available right now" and render '—'.
 */
export function altitudeFromPressureHpa(p_hpa: number | null | undefined): number | null {
    if (p_hpa === null || p_hpa === undefined) return null;
    if (!Number.isFinite(p_hpa)) return null;
    const p_pa = p_hpa * 100.0;

    /* Bounds: equate to refusing-to-extrapolate. P0_PA is sea-level. */
    if (p_pa > P0_PA) return null;

    /* Find the pressure top of the table by computing pressure(H_MAX_M). */
    const top = LAYERS[LAYERS.length - 1];
    let p_top: number;
    if (top.lapse_K_per_m === 0.0) {
        p_top = top.P_base_Pa * Math.exp(
            -G0_M_S2 * (H_MAX_M - top.h_base_m) / (R_AIR_J_KG_K * top.T_base_K)
        );
    } else {
        const T_at_top = top.T_base_K + top.lapse_K_per_m * (H_MAX_M - top.h_base_m);
        p_top = top.P_base_Pa * Math.pow(
            T_at_top / top.T_base_K,
            -G0_M_S2 / (R_AIR_J_KG_K * top.lapse_K_per_m)
        );
    }
    if (p_pa < p_top) return null;

    /* Pressure decreases monotonically with altitude. Walk layers
     * bottom-up and find the one whose [P_top, P_base] bracket contains
     * the input. Then invert that layer's barometric formula analytically. */
    for (let i = 0; i < LAYERS.length; i++) {
        const layer = LAYERS[i];
        const upper_P = i + 1 < LAYERS.length ? LAYERS[i + 1].P_base_Pa : p_top;
        if (p_pa <= layer.P_base_Pa && p_pa >= upper_P) {
            if (layer.lapse_K_per_m === 0.0) {
                return layer.h_base_m + (
                    -R_AIR_J_KG_K * layer.T_base_K / G0_M_S2
                    * Math.log(p_pa / layer.P_base_Pa)
                );
            }
            const ratio = Math.pow(
                p_pa / layer.P_base_Pa,
                -R_AIR_J_KG_K * layer.lapse_K_per_m / G0_M_S2
            );
            return layer.h_base_m + layer.T_base_K / layer.lapse_K_per_m * (ratio - 1.0);
        }
    }
    /* Should be unreachable for any p_pa within [p_top, P0_PA]. */
    return null;
}

/* Useful constants for callers that want them. */
export const ISA_SEA_LEVEL_PRESSURE_HPA = P0_PA / 100.0;
export const ISA_MAX_SUPPORTED_ALTITUDE_M = H_MAX_M;
