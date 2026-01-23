import type { WindVector, GridPoint, WindField } from "./types"

export function interpolateWind(
  lat: number,
  lon: number,
  grid: GridPoint[],
  bounds: WindField["bounds"],
  gridResolution: number,
): WindVector {
  // Find the four surrounding grid points
  const latIdx = (lat - bounds.latMin) / gridResolution
  const lonIdx = (lon - bounds.lonMin) / gridResolution

  const lat0 = Math.floor(latIdx)
  const lat1 = Math.ceil(latIdx)
  const lon0 = Math.floor(lonIdx)
  const lon1 = Math.ceil(lonIdx)

  const latFrac = latIdx - lat0
  const lonFrac = lonIdx - lon0

  // Get grid dimensions
  const lonCount = Math.ceil((bounds.lonMax - bounds.lonMin) / gridResolution) + 1

  const getPoint = (latI: number, lonI: number): WindVector => {
    const idx = latI * lonCount + lonI
    return grid[idx]?.wind || { u: 0, v: 0 }
  }

  // Bilinear interpolation
  const w00 = getPoint(lat0, lon0)
  const w01 = getPoint(lat0, lon1)
  const w10 = getPoint(lat1, lon0)
  const w11 = getPoint(lat1, lon1)

  const u =
    w00.u * (1 - latFrac) * (1 - lonFrac) +
    w01.u * (1 - latFrac) * lonFrac +
    w10.u * latFrac * (1 - lonFrac) +
    w11.u * latFrac * lonFrac

  const v =
    w00.v * (1 - latFrac) * (1 - lonFrac) +
    w01.v * (1 - latFrac) * lonFrac +
    w10.v * latFrac * (1 - lonFrac) +
    w11.v * latFrac * lonFrac

  return { u, v }
}

export function windSpeed(wind: WindVector): number {
  return Math.sqrt(wind.u * wind.u + wind.v * wind.v)
}

export function windDirection(wind: WindVector): number {
  return (Math.atan2(-wind.u, -wind.v) * 180) / Math.PI + 180
}

export function latLonToCanvas(
  lat: number,
  lon: number,
  bounds: { latMin: number; latMax: number; lonMin: number; lonMax: number },
  width: number,
  height: number,
): { x: number; y: number } {
  const x = ((lon - bounds.lonMin) / (bounds.lonMax - bounds.lonMin)) * width
  const y = ((bounds.latMax - lat) / (bounds.latMax - bounds.latMin)) * height
  return { x, y }
}

export function canvasToLatLon(
  x: number,
  y: number,
  bounds: { latMin: number; latMax: number; lonMin: number; lonMax: number },
  width: number,
  height: number,
): { lat: number; lon: number } {
  const lon = (x / width) * (bounds.lonMax - bounds.lonMin) + bounds.lonMin
  const lat = bounds.latMax - (y / height) * (bounds.latMax - bounds.latMin)
  return { lat, lon }
}
