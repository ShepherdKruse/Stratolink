import * as THREE from "three"
import type { LatLon } from "./types"

export const EARTH_RADIUS_KM = 6371
export const EARTH_SCENE_RADIUS = 1
export const ALTITUDE_EXAGGERATION = 12
export const DEFAULT_BALLOON_ALT_KM = 15
export const DEFAULT_COVERAGE_RADIUS_KM = 437

export function latLonToVec3(
  lat: number,
  lon: number,
  radiusScene: number = EARTH_SCENE_RADIUS,
): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lon + 180) * (Math.PI / 180)
  const x = -radiusScene * Math.sin(phi) * Math.cos(theta)
  const z = radiusScene * Math.sin(phi) * Math.sin(theta)
  const y = radiusScene * Math.cos(phi)
  return new THREE.Vector3(x, y, z)
}

export function balloonSceneAltitude(altKm: number): number {
  return (
    EARTH_SCENE_RADIUS + (altKm / EARTH_RADIUS_KM) * ALTITUDE_EXAGGERATION
  )
}

/**
 * Line-of-sight horizon distance for a balloon at altitude h over a spherical
 * Earth. Matches the simulation/balloon_sim formula. Returned in km.
 */
export function horizonDistanceKm(altitudeKm: number): number {
  return Math.sqrt(2 * EARTH_RADIUS_KM * altitudeKm + altitudeKm * altitudeKm)
}

/** Half-angle (in radians) subtended at Earth's centre by the coverage disc. */
export function coverageHalfAngle(altitudeKm: number): number {
  return Math.acos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitudeKm))
}

/** Seeded pseudo-random generator for stable fleet layouts. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Advance a lat/lon point by a given velocity in km-east/km-north over dt hours.
 * Uses a simple local-flat approximation; sufficient for short step sizes used
 * in the decorative fleet drift animation.
 */
export function advanceLatLon(
  p: LatLon,
  velocityEastKmH: number,
  velocityNorthKmH: number,
  dtHours: number,
): LatLon {
  const kmPerDegLat = 111.111
  const kmPerDegLon = Math.max(
    10,
    111.111 * Math.cos((p.lat * Math.PI) / 180),
  )
  const dLat = (velocityNorthKmH * dtHours) / kmPerDegLat
  const dLon = (velocityEastKmH * dtHours) / kmPerDegLon
  let lat = p.lat + dLat
  let lon = p.lon + dLon
  if (lat > 85) lat = 85
  if (lat < -85) lat = -85
  if (lon > 180) lon -= 360
  if (lon < -180) lon += 360
  return { lat, lon }
}
