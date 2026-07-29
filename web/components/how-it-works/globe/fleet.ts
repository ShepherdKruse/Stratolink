import type { BalloonState, LatLon } from "./types"
import { advanceLatLon, mulberry32 } from "./utils"

type FleetOptions = {
  size: number
  timeHours: number
  trailPoints?: number
  seed?: number
}

/**
 * Deterministically generates a fleet of balloons with wind-like drift trails.
 * The positions are procedural — good enough for a decorative visualisation
 * without needing live wind data in the browser.
 */
export function generateFleet({
  size,
  timeHours,
  trailPoints = 18,
  seed = 42,
}: FleetOptions): BalloonState[] {
  const rand = mulberry32(seed)
  const balloons: BalloonState[] = []

  for (let i = 0; i < size; i++) {
    const startLat = (rand() - 0.5) * 120
    const startLon = (rand() - 0.5) * 360
    const baseSpeed = 60 + rand() * 80
    const jetLat = 15 + rand() * 30
    const hemisphere = startLat >= 0 ? 1 : -1

    const velocityNorth = (rand() - 0.5) * 10
    const velocityEast =
      baseSpeed *
      (1 - Math.min(1, Math.abs(Math.abs(startLat) - jetLat) / 40)) *
      hemisphere *
      0.8 +
      baseSpeed * 0.4

    let point: LatLon = { lat: startLat, lon: startLon }
    const trail: LatLon[] = [point]
    const totalSteps = trailPoints
    const stepHours = timeHours / Math.max(1, totalSteps)

    for (let s = 0; s < totalSteps; s++) {
      const jitter = (rand() - 0.5) * 8
      point = advanceLatLon(
        point,
        velocityEast + jitter,
        velocityNorth + jitter * 0.2,
        stepHours,
      )
      trail.push(point)
    }

    balloons.push({
      id: `B${i.toString().padStart(2, "0")}`,
      position: trail[trail.length - 1],
      altitudeKm: 12 + rand() * 8,
      trail,
    })
  }

  return balloons
}
