"use client"

import { useMemo, useState } from "react"
import {
  EARTH_RADIUS_KM,
  horizonDistanceKm,
} from "./globe/utils"

const MIN_ALT = 8
const MAX_ALT = 25
const DEFAULT_ALT = 15

/**
 * Interactive cross-section: drag the altitude slider to watch the
 * line-of-sight horizon, coverage radius, and footprint area update in
 * real time. Uses the same formulae as balloon_sim/coverage.py.
 */
export function SingleBalloonScene() {
  const [altitudeKm, setAltitudeKm] = useState(DEFAULT_ALT)

  const { horizonKm, footprintKm2, halfAngleDeg } = useMemo(() => {
    const R = EARTH_RADIUS_KM
    const horizon = horizonDistanceKm(altitudeKm)
    const halfAngle = Math.acos(R / (R + altitudeKm))
    const capHeight = R * (1 - Math.cos(halfAngle))
    const footprint = 2 * Math.PI * R * capHeight
    return {
      horizonKm: horizon,
      footprintKm2: footprint,
      halfAngleDeg: (halfAngle * 180) / Math.PI,
    }
  }, [altitudeKm])

  // Scene geometry (normalised units — Earth radius = 360)
  const earthR = 360
  const altScenePx = (altitudeKm / EARTH_RADIUS_KM) * earthR * 22
  const cx = 400
  const cy = 470
  const balloonX = cx
  const balloonY = cy - earthR - altScenePx

  // Tangent points (horizon) — geometry on the circle
  const distCenterToBalloon = earthR + altScenePx
  const tangentLen = Math.sqrt(
    distCenterToBalloon * distCenterToBalloon - earthR * earthR,
  )
  const sinA = earthR / distCenterToBalloon
  const cosA = tangentLen / distCenterToBalloon
  const tangentRightX = balloonX + tangentLen * cosA
  const tangentRightY = balloonY + tangentLen * sinA
  const tangentLeftX = balloonX - tangentLen * cosA
  const tangentLeftY = balloonY + tangentLen * sinA
  // Horizon points on surface of Earth
  const surfaceRightX =
    cx +
    earthR * (tangentRightX - cx) / distCenterToBalloon -
    earthR * (balloonY - cy) / distCenterToBalloon * 0 // simplified projection
  // Correct horizon points using geometry: the tangent-from-balloon touches
  // the circle at points we can compute directly.
  // Horizon point = balloon_pos rotated toward center by angle B - A
  const B = Math.atan2(balloonY - cy, balloonX - cx) // = -π/2 since directly above
  const hAng = Math.asin(earthR / distCenterToBalloon)
  const angRight = B + (Math.PI / 2 - hAng)
  const angLeft = B - (Math.PI / 2 - hAng)
  const horizonRX = cx + earthR * Math.cos(angRight)
  const horizonRY = cy + earthR * Math.sin(angRight)
  const horizonLX = cx + earthR * Math.cos(angLeft)
  const horizonLY = cy + earthR * Math.sin(angLeft)

  return (
    <div className="rounded-sm border border-border bg-card p-6 shadow-sm sm:p-10">
      <div className="grid gap-10 lg:grid-cols-[1fr_260px]">
        <div>
          <svg
            viewBox="0 0 800 520"
            className="w-full text-foreground/80"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <radialGradient id="earthFill" cx="0.5" cy="0.35" r="0.8">
                <stop offset="0%" stopColor="#d6dee7" stopOpacity="0.45" />
                <stop offset="100%" stopColor="#9fb2c3" stopOpacity="0.2" />
              </radialGradient>
              <linearGradient id="coverageFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="currentColor" stopOpacity="0.18" />
                <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
              </linearGradient>
            </defs>

            <circle cx={cx} cy={cy} r={earthR} fill="url(#earthFill)" />
            <circle
              cx={cx}
              cy={cy}
              r={earthR}
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.25"
              strokeWidth="1"
            />

            {/* Surface label */}
            <text
              x={cx}
              y={cy + earthR - 16}
              fontSize="11"
              textAnchor="middle"
              fill="currentColor"
              opacity="0.45"
              fontFamily="sans-serif"
            >
              Earth · R = 6,371 km
            </text>

            {/* Coverage arc on surface (highlighted) */}
            <path
              d={describeArc(
                cx,
                cy,
                earthR,
                (angLeft * 180) / Math.PI,
                (angRight * 180) / Math.PI,
              )}
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeOpacity="0.75"
            />

            {/* Footprint fill */}
            <path
              d={`${describeArc(
                cx,
                cy,
                earthR,
                (angLeft * 180) / Math.PI,
                (angRight * 180) / Math.PI,
              )} L ${balloonX} ${balloonY} Z`}
              fill="url(#coverageFill)"
              stroke="none"
            />

            {/* Tangent lines (line-of-sight rays) */}
            <line
              x1={balloonX}
              y1={balloonY}
              x2={horizonRX}
              y2={horizonRY}
              stroke="currentColor"
              strokeWidth="1"
              strokeOpacity="0.55"
              strokeDasharray="3 3"
            />
            <line
              x1={balloonX}
              y1={balloonY}
              x2={horizonLX}
              y2={horizonLY}
              stroke="currentColor"
              strokeWidth="1"
              strokeOpacity="0.55"
              strokeDasharray="3 3"
            />

            {/* Altitude annotation */}
            <line
              x1={balloonX - 6}
              y1={balloonY}
              x2={balloonX - 6}
              y2={cy - earthR}
              stroke="currentColor"
              strokeWidth="1"
              strokeOpacity="0.4"
            />
            <text
              x={balloonX - 14}
              y={(balloonY + cy - earthR) / 2}
              fontSize="11"
              textAnchor="end"
              fill="currentColor"
              opacity="0.7"
              fontFamily="sans-serif"
            >
              {altitudeKm.toFixed(0)} km
            </text>

            {/* Balloon marker */}
            <circle cx={balloonX} cy={balloonY} r="5" fill="currentColor" />
            <circle
              cx={balloonX}
              cy={balloonY}
              r="11"
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.3"
              strokeWidth="1"
            />
            <text
              x={balloonX + 14}
              y={balloonY + 4}
              fontSize="11"
              fill="currentColor"
              opacity="0.75"
              fontFamily="sans-serif"
            >
              Stratolink payload
            </text>

            {/* Horizon markers */}
            <circle cx={horizonRX} cy={horizonRY} r="3" fill="currentColor" />
            <circle cx={horizonLX} cy={horizonLY} r="3" fill="currentColor" />
            <text
              x={horizonRX + 6}
              y={horizonRY + 14}
              fontSize="10"
              fill="currentColor"
              opacity="0.55"
              fontFamily="sans-serif"
            >
              horizon
            </text>
          </svg>
        </div>

        <div className="flex flex-col justify-between gap-8">
          <div className="space-y-5">
            <ValueRow
              label="Altitude"
              value={`${altitudeKm.toFixed(0)} km`}
            />
            <ValueRow
              label="Horizon"
              value={`${Math.round(horizonKm).toLocaleString()} km`}
              hint="d = √(2·R·h + h²)"
            />
            <ValueRow
              label="Footprint"
              value={`${(footprintKm2 / 1e6).toFixed(2)}M km²`}
              hint={`${halfAngleDeg.toFixed(1)}° half-angle`}
            />
            <ValueRow
              label="Uplink cadence"
              value="20 min"
              hint="40-byte LoRaWAN frame"
            />
          </div>

          <div>
            <label className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
              Operational altitude
            </label>
            <input
              type="range"
              min={MIN_ALT}
              max={MAX_ALT}
              step={1}
              value={altitudeKm}
              onChange={(e) => setAltitudeKm(parseInt(e.target.value, 10))}
              className="mt-3 w-full accent-foreground"
            />
            <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
              <span>{MIN_ALT} km</span>
              <span>{MAX_ALT} km</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ValueRow({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="border-b border-border pb-4">
      <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-xl font-light tracking-tight text-foreground">
        {value}
      </div>
      {hint && (
        <div className="mt-1 font-mono text-[11px] text-muted-foreground/80">
          {hint}
        </div>
      )}
    </div>
  )
}

function describeArc(
  cx: number,
  cy: number,
  r: number,
  startDeg: number,
  endDeg: number,
): string {
  const startRad = (startDeg * Math.PI) / 180
  const endRad = (endDeg * Math.PI) / 180
  const x1 = cx + r * Math.cos(startRad)
  const y1 = cy + r * Math.sin(startRad)
  const x2 = cx + r * Math.cos(endRad)
  const y2 = cy + r * Math.sin(endRad)
  const largeArc = endDeg - startDeg <= 180 ? 0 : 1
  const sweep = 1
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} ${sweep} ${x2} ${y2}`
}
