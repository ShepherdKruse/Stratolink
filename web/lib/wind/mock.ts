import type { WindField, GridPoint } from "./types"

// Seeded random number generator for deterministic results
function seededRandom(seed: number) {
  return () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
}

export function generateMockWindField(altitudeBand: "5km" | "15km" = "15km", seed = 12345): WindField {
  const random = seededRandom(seed)

  const bounds = {
    latMin: 30,
    latMax: 50,
    lonMin: -130,
    lonMax: -100,
  }

  const gridResolution = 2
  const grid: GridPoint[] = []

  // Base wind parameters vary by altitude
  const baseU = altitudeBand === "15km" ? 15 : 8
  const baseV = altitudeBand === "15km" ? 3 : 2
  const variability = altitudeBand === "15km" ? 8 : 5

  for (let lat = bounds.latMin; lat <= bounds.latMax; lat += gridResolution) {
    for (let lon = bounds.lonMin; lon <= bounds.lonMax; lon += gridResolution) {
      // Create realistic wind patterns with some spatial correlation
      const latFactor = Math.sin(((lat - bounds.latMin) / (bounds.latMax - bounds.latMin)) * Math.PI)
      const lonFactor = Math.cos(((lon - bounds.lonMin) / (bounds.lonMax - bounds.lonMin)) * Math.PI * 0.5)

      const u = baseU + variability * latFactor + (random() - 0.5) * 4
      const v = baseV + variability * 0.3 * lonFactor + (random() - 0.5) * 3

      grid.push({
        lat,
        lon,
        wind: { u, v },
      })
    }
  }

  return {
    timestamp: new Date().toISOString(),
    altitudeBand,
    grid,
    gridResolution,
    bounds,
  }
}
