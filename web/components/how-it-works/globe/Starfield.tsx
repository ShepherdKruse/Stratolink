"use client"

import { useMemo } from "react"
import * as THREE from "three"
import { mulberry32 } from "./utils"

/**
 * Static backdrop of 900 points on a distant inverted sphere. Cheap,
 * non-animated — purely for depth cues.
 */
export function Starfield() {
  const positions = useMemo(() => {
    const rand = mulberry32(17)
    const count = 900
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const theta = rand() * Math.PI * 2
      const phi = Math.acos(2 * rand() - 1)
      const R = 40 + rand() * 6
      arr[i * 3 + 0] = R * Math.sin(phi) * Math.cos(theta)
      arr[i * 3 + 1] = R * Math.sin(phi) * Math.sin(theta)
      arr[i * 3 + 2] = R * Math.cos(phi)
    }
    return arr
  }, [])

  return (
    <points>
      <bufferGeometry attach="geometry">
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={positions.length / 3}
        />
      </bufferGeometry>
      <pointsMaterial
        color="#cbd5e1"
        size={0.05}
        sizeAttenuation
        transparent
        opacity={0.55}
      />
    </points>
  )
}
