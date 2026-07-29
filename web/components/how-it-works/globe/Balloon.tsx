"use client"

import { useMemo } from "react"
import * as THREE from "three"
import { balloonSceneAltitude, latLonToVec3 } from "./utils"

type Props = {
  lat: number
  lon: number
  altitudeKm: number
  accent?: boolean
}

export function Balloon({ lat, lon, altitudeKm, accent = false }: Props) {
  const position = useMemo(() => {
    const altScene = balloonSceneAltitude(altitudeKm)
    return latLonToVec3(lat, lon, altScene)
  }, [lat, lon, altitudeKm])

  const surface = useMemo(() => latLonToVec3(lat, lon, 1.0), [lat, lon])

  const color = accent ? "#8ab8ff" : "#e6edf3"

  return (
    <group>
      {/* Tether line from surface to balloon */}
      <line>
        <bufferGeometry attach="geometry">
          <bufferAttribute
            attach="attributes-position"
            args={[
              new Float32Array([
                surface.x,
                surface.y,
                surface.z,
                position.x,
                position.y,
                position.z,
              ]),
              3,
            ]}
            count={2}
          />
        </bufferGeometry>
        <lineBasicMaterial
          color={color}
          transparent
          opacity={accent ? 0.35 : 0.18}
        />
      </line>

      <mesh position={position}>
        <sphereGeometry args={[0.01, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>

      <mesh position={position}>
        <sphereGeometry args={[0.022, 16, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={accent ? 0.35 : 0.18}
        />
      </mesh>
    </group>
  )
}
