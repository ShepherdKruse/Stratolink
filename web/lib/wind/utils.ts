import type { WindVector, WindField } from "./types"

/** Index grid points by snapped lat/lon cell (API coords may differ slightly from request). */
export function buildWindLookup(field: WindField): Map<string, WindVector> {
  const lookup = new Map<string, WindVector>()
  const { bounds, gridResolution, grid } = field
  for (const p of grid) {
    const li = Math.round((p.lat - bounds.latMin) / gridResolution)
    const lj = Math.round((p.lon - bounds.lonMin) / gridResolution)
    lookup.set(`${li},${lj}`, p.wind)
  }
  return lookup
}

export function interpolateWind(
  lat: number,
  lon: number,
  lookup: Map<string, WindVector>,
  bounds: WindField["bounds"],
  gridResolution: number,
): WindVector {
  const latIdx = (lat - bounds.latMin) / gridResolution
  const lonIdx = (lon - bounds.lonMin) / gridResolution

  const lat0 = Math.floor(latIdx)
  const lat1 = lat0 + 1
  const lon0 = Math.floor(lonIdx)
  const lon1 = lon0 + 1

  const latFrac = latIdx - lat0
  const lonFrac = lonIdx - lon0

  const getPoint = (latI: number, lonI: number): WindVector =>
    lookup.get(`${latI},${lonI}`) ?? { u: 0, v: 0 }

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
