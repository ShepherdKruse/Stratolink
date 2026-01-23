export interface WindVector {
  u: number // eastward component (m/s)
  v: number // northward component (m/s)
}

export interface GridPoint {
  lat: number
  lon: number
  wind: WindVector
}

export interface WindField {
  timestamp: string
  altitudeBand: "5km" | "15km"
  grid: GridPoint[]
  gridResolution: number
  bounds: {
    latMin: number
    latMax: number
    lonMin: number
    lonMax: number
  }
}

export interface TrajectoryPoint {
  lat: number
  lon: number
  timestamp: string
  altitude: number
  source: "observed" | "predicted"
}

export interface BalloonTrajectory {
  balloonId: string
  launchSite: string
  launchTime: string
  altitudeBand: "5km" | "15km"
  points: TrajectoryPoint[]
  status: "active" | "completed" | "predicted"
}

export interface Particle {
  x: number
  y: number
  age: number
  maxAge: number
  speed: number
}
