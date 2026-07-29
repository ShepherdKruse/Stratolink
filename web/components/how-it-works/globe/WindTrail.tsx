"use client"

import { useMemo } from "react"
import * as THREE from "three"
import type { LatLon } from "./types"
import { latLonToVec3 } from "./utils"

type Props = {
  points: LatLon[]
}

/**
 * Renders a balloon's past trail as a series of short line segments whose
 * opacity fades from head to tail. Each segment sits just above Earth's
 * surface so it's visible without z-fighting.
 */
export function WindTrail({ points }: Props) {
  const { positions, colors } = useMemo(() => {
    if (points.length < 2) {
      return {
        positions: new Float32Array(),
        colors: new Float32Array(),
      }
    }
    const pos: number[] = []
    const col: number[] = []
    for (let i = 0; i < points.length - 1; i++) {
      const a = latLonToVec3(
        points[i].lat,
        points[i].lon,
        1.004,
      )
      const b = latLonToVec3(
        points[i + 1].lat,
        points[i + 1].lon,
        1.004,
      )
      const tA = i / (points.length - 1)
      const tB = (i + 1) / (points.length - 1)
      pos.push(a.x, a.y, a.z, b.x, b.y, b.z)
      col.push(tA, tA, tA, tB, tB, tB)
    }
    return {
      positions: new Float32Array(pos),
      colors: new Float32Array(col),
    }
  }, [points])

  if (positions.length === 0) return null

  return (
    <lineSegments>
      <bufferGeometry attach="geometry">
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={positions.length / 3}
        />
        <bufferAttribute
          attach="attributes-color"
          args={[colors, 3]}
          count={colors.length / 3}
        />
      </bufferGeometry>
      <lineBasicMaterial
        vertexColors
        transparent
        opacity={0.7}
        blending={THREE.AdditiveBlending}
      />
    </lineSegments>
  )
}
