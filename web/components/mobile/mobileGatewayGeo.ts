import type { GatewayReception } from '../dashboard-v2/atoms';
import { isUsableGpsCoordinate } from '@/lib/mapGeo';

export function parseGateways(raw: unknown): GatewayReception[] | null {
    if (!raw) return null;
    let arr: unknown = raw;
    if (typeof raw === 'string') {
        try {
            arr = JSON.parse(raw);
        } catch {
            return null;
        }
    }
    if (!Array.isArray(arr)) return null;
    const out: GatewayReception[] = [];
    for (const item of arr) {
        if (!item || typeof item !== 'object') continue;
        const o = item as Record<string, unknown>;
        if (typeof o.gateway_id !== 'string') continue;
        const lat = coerceNum(o.lat);
        const lon = coerceNum(o.lon);
        out.push({
            gateway_id: o.gateway_id,
            rssi: coerceNum(o.rssi),
            snr: coerceNum(o.snr),
            lat,
            lon,
            alt: coerceNum(o.alt),
        });
    }
    return out;
}

function coerceNum(v: unknown): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
}

/** Gateways with a real WGS84 position (Packet Broker entries excluded). */
export function gatewaysWithLocation(gateways: GatewayReception[] | null | undefined): GatewayReception[] {
    if (!gateways?.length) return [];
    return gateways.filter(
        (g) => g.lat != null && g.lon != null && isUsableGpsCoordinate(g.lat, g.lon),
    );
}

export function buildGatewaysGeoJSON(gateways: GatewayReception[]): GeoJSON.FeatureCollection {
    return {
        type: 'FeatureCollection',
        features: gateways.map((g) => ({
            type: 'Feature',
            id: g.gateway_id,
            geometry: { type: 'Point', coordinates: [g.lon!, g.lat!] },
            properties: {
                gateway_id: g.gateway_id,
                rssi: g.rssi ?? -130,
            },
        })),
    };
}

export function buildReceptionLinesGeoJSON(
    balloonLat: number,
    balloonLon: number,
    gateways: GatewayReception[],
): GeoJSON.FeatureCollection | null {
    if (!gateways.length) return null;
    return {
        type: 'FeatureCollection',
        features: gateways.map((g) => ({
            type: 'Feature',
            geometry: {
                type: 'LineString',
                coordinates: [
                    [balloonLon, balloonLat],
                    [g.lon!, g.lat!],
                ],
            },
            properties: { rssi: g.rssi ?? -130 },
        })),
    };
}

/** Haversine distance in km (for the ranked list). */
export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const dφ = ((lat2 - lat1) * Math.PI) / 180;
    const dλ = ((lon2 - lon1) * Math.PI) / 180;
    const a = Math.sin(dφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(dλ / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const Δλ = ((lon2 - lon1) * Math.PI) / 180;
    const y = Math.sin(Δλ) * Math.cos(φ2);
    const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
    const θ = Math.atan2(y, x);
    return ((θ * 180) / Math.PI + 360) % 360;
}

export function rssiBarFill(rssi: number | null): number {
    if (rssi == null || !Number.isFinite(rssi)) return 0.04;
    const lo = -125;
    const hi = -85;
    const clamped = Math.max(lo, Math.min(hi, rssi));
    return Math.max(0.04, Math.min(1, (clamped - lo) / (hi - lo)));
}

export function rssiTierLabel(rssi: number): string {
    if (rssi >= -85) return 'strong';
    if (rssi >= -100) return 'good';
    if (rssi >= -110) return 'fair';
    if (rssi >= -125) return 'weak';
    return 'marginal';
}
