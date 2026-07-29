export type LatLon = { lat: number; lon: number }

export type BalloonState = {
  id: string
  position: LatLon
  altitudeKm: number
  trail: LatLon[]
}

export type GlobeConfig = {
  fleetSize: number
  showCoverage: boolean
  showTrails: boolean
  timeHours: number
}
