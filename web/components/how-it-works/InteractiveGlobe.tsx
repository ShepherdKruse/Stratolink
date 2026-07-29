"use client"

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { Canvas, useFrame } from "@react-three/fiber"
import { OrbitControls, PerspectiveCamera } from "@react-three/drei"
import type * as THREE from "three"
import { Earth } from "./globe/Earth"
import { Balloon } from "./globe/Balloon"
import { CoverageDisc } from "./globe/CoverageDisc"
import { WindTrail } from "./globe/WindTrail"
import { Starfield } from "./globe/Starfield"
import { generateFleet } from "./globe/fleet"
import {
  DEFAULT_BALLOON_ALT_KM,
  horizonDistanceKm,
} from "./globe/utils"

const FLEET_PRESETS = [1, 4, 12, 24] as const

type AutoRotatingSceneProps = {
  children: React.ReactNode
}

function AutoRotatingScene({ children }: AutoRotatingSceneProps) {
  const ref = useRef<THREE.Group>(null)
  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.04
    }
  })
  return <group ref={ref}>{children}</group>
}

export function InteractiveGlobe() {
  const [fleetSize, setFleetSize] = useState<number>(12)
  const [showCoverage, setShowCoverage] = useState(true)
  const [showTrails, setShowTrails] = useState(true)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const fleet = useMemo(
    () => generateFleet({ size: fleetSize, timeHours: 36 }),
    [fleetSize],
  )

  const coverageKm = Math.round(horizonDistanceKm(DEFAULT_BALLOON_ALT_KM))

  const coveragePctEarth = useMemo(() => {
    // Earth surface area = 4πR². Each cap area = 2πRh where h = R(1 − cos θ).
    const totalCapArea = fleet.reduce((sum, b) => {
      const R = 6371
      const h = R * (1 - Math.cos(Math.acos(R / (R + b.altitudeKm))))
      const capArea = 2 * Math.PI * R * h
      return sum + capArea
    }, 0)
    const earthArea = 4 * Math.PI * 6371 * 6371
    const overlap = Math.min(0.55, fleetSize * 0.012)
    const effectiveCoverage = (totalCapArea / earthArea) * (1 - overlap)
    return Math.min(99, effectiveCoverage * 100)
  }, [fleet, fleetSize])

  const handleHover = useCallback(
    (id: string | null) => setHoveredId(id),
    [],
  )

  return (
    <div className="overflow-hidden rounded-sm border border-white/10 bg-[#05080f]">
      <div className="relative grid lg:grid-cols-[1fr_320px]">
        <div className="relative h-[520px] lg:h-[640px]">
          {mounted && (
            <Canvas dpr={[1, 2]} gl={{ antialias: true, alpha: false }}>
              <color attach="background" args={["#05080f"]} />
              <PerspectiveCamera
                makeDefault
                position={[0, 0.3, 3.1]}
                fov={38}
              />
              <ambientLight intensity={0.45} />
              <directionalLight
                position={[4, 2, 4]}
                intensity={1.6}
                color="#f5f1e6"
              />
              <directionalLight
                position={[-3, -1, -2]}
                intensity={0.25}
                color="#3b5a75"
              />
              <Suspense fallback={null}>
                <Starfield />
                <AutoRotatingScene>
                  <Earth />
                  {showTrails &&
                    fleet.map((b) => (
                      <WindTrail key={`t-${b.id}`} points={b.trail} />
                    ))}
                  {showCoverage &&
                    fleet.map((b) => (
                      <CoverageDisc
                        key={`c-${b.id}`}
                        lat={b.position.lat}
                        lon={b.position.lon}
                        altitudeKm={b.altitudeKm}
                        accent={hoveredId === b.id}
                      />
                    ))}
                  {fleet.map((b) => (
                    <Balloon
                      key={`b-${b.id}`}
                      lat={b.position.lat}
                      lon={b.position.lon}
                      altitudeKm={b.altitudeKm}
                      accent={hoveredId === b.id}
                    />
                  ))}
                </AutoRotatingScene>
              </Suspense>
              <OrbitControls
                enablePan={false}
                enableDamping
                dampingFactor={0.08}
                rotateSpeed={0.55}
                minDistance={1.6}
                maxDistance={6}
                autoRotate={false}
              />
            </Canvas>
          )}
          <div className="pointer-events-none absolute bottom-4 left-4 text-[11px] font-light tracking-wide text-white/40">
            Drag to rotate · scroll to zoom
          </div>
        </div>

        <aside className="flex flex-col justify-between gap-6 border-t border-white/10 p-6 text-white/85 lg:border-l lg:border-t-0 lg:p-8">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-white/40">
              Live Fleet
            </div>
            <div className="mt-6 space-y-6">
              <Readout
                label="Balloons"
                value={fleetSize.toString()}
                hint="stratospheric platforms"
              />
              <Readout
                label="Operational altitude"
                value={`12–20 km`}
                hint="above jet stream / below LEO"
              />
              <Readout
                label="Coverage per balloon"
                value={`~${coverageKm.toLocaleString()} km radius`}
                hint="line-of-sight horizon"
              />
              <Readout
                label="Fleet footprint"
                value={`${coveragePctEarth.toFixed(1)}% of Earth`}
                hint="instantaneous, overlap-adjusted"
              />
            </div>
          </div>

          <div className="space-y-5">
            <div>
              <div className="mb-3 text-[10px] font-medium uppercase tracking-[0.2em] text-white/40">
                Fleet size
              </div>
              <div className="flex gap-1.5">
                {FLEET_PRESETS.map((n) => (
                  <button
                    key={n}
                    onClick={() => setFleetSize(n)}
                    className={`flex-1 rounded-sm border px-2 py-2 text-xs font-light tracking-wide transition-all ${
                      fleetSize === n
                        ? "border-white/60 bg-white/10 text-white"
                        : "border-white/10 bg-transparent text-white/50 hover:border-white/30 hover:text-white/80"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Toggle
                label="Coverage footprint"
                active={showCoverage}
                onChange={setShowCoverage}
              />
              <Toggle
                label="Wind-drift trails"
                active={showTrails}
                onChange={setShowTrails}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 border-t border-white/10 pt-4 text-[11px] font-light leading-relaxed text-white/45">
            <span>
              Each balloon independently uplinks a 40-byte telemetry frame on
              every wake cycle.
            </span>
          </div>
        </aside>
      </div>

      {hoveredId !== null && (
        <span className="sr-only">Hovered balloon {hoveredId}</span>
      )}
    </div>
  )
}

function Readout({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">
        {label}
      </div>
      <div className="mt-1 font-light tracking-tight text-white text-xl">
        {value}
      </div>
      {hint && <div className="mt-1 text-[11px] text-white/40">{hint}</div>}
    </div>
  )
}

function Toggle({
  label,
  active,
  onChange,
}: {
  label: string
  active: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <button
      onClick={() => onChange(!active)}
      className="flex w-full items-center justify-between rounded-sm border border-white/10 px-3 py-2 text-left text-xs font-light text-white/70 transition-all hover:border-white/30 hover:text-white"
    >
      <span>{label}</span>
      <span
        className={`relative h-4 w-7 rounded-full transition-colors ${
          active ? "bg-white/80" : "bg-white/15"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-[#05080f] transition-all ${
            active ? "left-3.5" : "left-0.5"
          }`}
        />
      </span>
    </button>
  )
}
