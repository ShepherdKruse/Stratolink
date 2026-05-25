/**
 * Balloon-centered gateway range math.
 *
 * Answers "should we be getting signal right now, and could a different
 * spreading factor help?" by turning the balloon's altitude + the nearest
 * gateway distance into spreading-factor reach rings and a plain-language
 * readout.
 *
 * Honesty notes (see the design spec):
 *  - SF7 range is the real, programmed reach. SF10 / SF12 are *estimates*
 *    (each SF step adds ~2.5–3 dB; free-space range roughly doubles per 6 dB).
 *  - Every ring is capped at the altitude-limited radio horizon, because a
 *    balloon with clear line of sight is often limited by the curve of the
 *    earth, not the link budget. Without the cap the SF12 ring would promise
 *    a link the horizon makes impossible.
 *  - SF_MULT values are reasonable defaults; correct them from field data.
 */

import type { Feature, Polygon } from 'geojson';

/**
 * SF7 reach in km — the range we actually fly today.
 *
 * Mirrors `COVERAGE_KM` in `scripts/refresh-ttnmapper-gateways.mjs` (the
 * per-gateway reception radius used to precompute the coverage union). That
 * script is the existing source of truth for "how far a gateway and balloon
 * can hear each other." Adjust here as field data refines it.
 */
export const SF7_RANGE_KM = 250;

/** SF reach relative to SF7. Approximate, environment-dependent. */
export const SF_MULT: Record<RingSf, number> = {
    sf7: 1.0,
    sf10: 1.8,
    sf12: 3.2,
};

export type RingSf = 'sf7' | 'sf10' | 'sf12';

/**
 * Altitude-limited radio horizon (km). Line-of-sight to a ground gateway is
 * ≈ 3.57·√(h_m). A balloon at ~9,500 m sees ~350 km regardless of link
 * budget. Returns Infinity for unknown/zero altitude so the link budget
 * governs in that case.
 */
export function horizonKm(altM: number | null | undefined): number {
    if (!altM || altM <= 0) return Infinity;
    return 3.57 * Math.sqrt(altM);
}

/** Final ring radius = min(link-budget reach, radio horizon). */
export function ringKm(sf: RingSf, altM: number | null | undefined): number {
    const budget = SF7_RANGE_KM * SF_MULT[sf];
    return Math.min(budget, horizonKm(altM));
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

export interface GatewayPoint {
    lat: number;
    lon: number;
}

export interface NearestGateway {
    lat: number;
    lon: number;
    distKm: number;
}

/** Closest gateway to (lat, lon), or null when the set is empty. */
export function nearestGateway(
    lat: number,
    lon: number,
    gateways: readonly GatewayPoint[],
): NearestGateway | null {
    let best: NearestGateway | null = null;
    for (const g of gateways) {
        const d = haversineKm(lat, lon, g.lat, g.lon);
        if (best === null || d < best.distKm) best = { lat: g.lat, lon: g.lon, distKm: d };
    }
    return best;
}

/**
 * Geodesic circle as a GeoJSON Polygon, centered on (lon, lat) at radiusKm.
 * Hand-rolled (vs. turf) so the client bundle stays lean. Walks `steps`
 * bearings using the great-circle destination formula.
 */
export function geodesicCircle(
    lon: number,
    lat: number,
    radiusKm: number,
    steps = 96,
): Feature<Polygon> {
    const R = 6371;
    const δ = radiusKm / R;
    const φ1 = (lat * Math.PI) / 180;
    const λ1 = (lon * Math.PI) / 180;
    const ring: [number, number][] = [];
    for (let i = 0; i <= steps; i++) {
        const θ = (i / steps) * 2 * Math.PI;
        const φ2 = Math.asin(Math.sin(φ1) * Math.cos(δ) + Math.cos(φ1) * Math.sin(δ) * Math.cos(θ));
        const λ2 =
            λ1 +
            Math.atan2(
                Math.sin(θ) * Math.sin(δ) * Math.cos(φ1),
                Math.cos(δ) - Math.sin(φ1) * Math.sin(φ2),
            );
        ring.push([((λ2 * 180) / Math.PI + 540) % 360 - 180, (φ2 * 180) / Math.PI]);
    }
    return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: {},
    };
}

export type SignalChip = 'ok' | 'maybe' | 'none';

export interface SignalReadout {
    chip: SignalChip;
    text: string;
}

/**
 * The plain-language answer: given the nearest gateway distance and the
 * balloon altitude, what link (if any) should we expect?
 */
export function signalReadout(distKm: number | null, altM: number | null | undefined): SignalReadout {
    if (distKm === null) {
        return { chip: 'none', text: 'No gateways loaded — cannot estimate signal.' };
    }
    const sf7 = ringKm('sf7', altM);
    const sf10 = ringKm('sf10', altM);
    const sf12 = ringKm('sf12', altM);
    const d = Math.round(distKm);
    if (distKm <= sf7) {
        return { chip: 'ok', text: `Nearest gateway ${d} km, within SF7 range — expect signal now.` };
    }
    if (distKm <= sf10) {
        return {
            chip: 'maybe',
            text: `Nearest gateway ${d} km, beyond SF7 but within SF10 reach. A link may be possible at a higher spreading factor.`,
        };
    }
    if (distKm <= sf12) {
        return {
            chip: 'maybe',
            text: `Nearest gateway ${d} km, only within SF12 reach. Marginal long-range link at best.`,
        };
    }
    const pastHorizon = distKm > horizonKm(altM);
    return {
        chip: 'none',
        text: `Nearest gateway ${d} km, beyond all ranges${pastHorizon ? ' and past the radio horizon' : ''}. Expect silence.`,
    };
}
