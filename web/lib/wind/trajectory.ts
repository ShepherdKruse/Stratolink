import type { WindField, BalloonTrajectory, TrajectoryPoint } from "./types"
import { interpolateWind } from "./utils"

export function integrateBalloonTrajectory(
  windField: WindField,
  startLat: number,
  startLon: number,
  durationHours = 24,
  timeStepMinutes = 30,
): TrajectoryPoint[] {
  const points: TrajectoryPoint[] = []
  let lat = startLat
  let lon = startLon

  const startTime = new Date()
  const steps = Math.floor((durationHours * 60) / timeStepMinutes)

  // Conversion factor: degrees per meter at equator (approximately)
  const metersPerDegreeLat = 111000

  for (let i = 0; i <= steps; i++) {
    const timestamp = new Date(startTime.getTime() + i * timeStepMinutes * 60 * 1000)

    points.push({
      lat,
      lon,
      timestamp: timestamp.toISOString(),
      altitude: windField.altitudeBand === "15km" ? 15000 : 5000,
      source: i === 0 ? "observed" : "predicted",
    })

    // Check if still within bounds
    if (
      lat < windField.bounds.latMin ||
      lat > windField.bounds.latMax ||
      lon < windField.bounds.lonMin ||
      lon > windField.bounds.lonMax
    ) {
      break
    }

    // Integrate position using wind field
    const wind = interpolateWind(lat, lon, windField.grid, windField.bounds, windField.gridResolution)

    // Convert wind (m/s) to position change (degrees)
    const dt = timeStepMinutes * 60 // seconds
    const dLon = (wind.u * dt) / (metersPerDegreeLat * Math.cos((lat * Math.PI) / 180))
    const dLat = (wind.v * dt) / metersPerDegreeLat

    lon += dLon
    lat += dLat
  }

  return points
}

export function generateMockTrajectories(windField: WindField, count = 3): BalloonTrajectory[] {
  const launchSites = [
    { name: "Reno, NV", lat: 39.5, lon: -119.8 },
    { name: "Albuquerque, NM", lat: 35.1, lon: -106.6 },
    { name: "Denver, CO", lat: 39.7, lon: -104.9 },
    { name: "Phoenix, AZ", lat: 33.4, lon: -112.0 },
    { name: "Salt Lake City, UT", lat: 40.7, lon: -111.9 },
  ]

  return launchSites.slice(0, count).map((site, idx) => {
    const points = integrateBalloonTrajectory(windField, site.lat, site.lon, 18, 20)

    return {
      balloonId: `SL-${String(idx + 1).padStart(3, "0")}`,
      launchSite: site.name,
      launchTime: new Date().toISOString(),
      altitudeBand: windField.altitudeBand,
      points,
      status: idx === 0 ? "active" : "predicted",
    }
  })
}
