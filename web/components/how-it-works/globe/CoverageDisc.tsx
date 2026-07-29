"use client"

import { useMemo } from "react"
import * as THREE from "three"
import {
  EARTH_SCENE_RADIUS,
  coverageHalfAngle,
  latLonToVec3,
} from "./utils"

type Props = {
  lat: number
  lon: number
  altitudeKm: number
  accent?: boolean
}

/**
 * Renders the spherical-cap footprint of a balloon's line-of-sight coverage
 * on Earth's surface, with a subtle outer ring so the edge is legible even
 * when the fill opacity is low.
 */
export function CoverageDisc({
  lat,
  lon,
  altitudeKm,
  accent = false,
}: Props) {
  const { capGeom, ringPositions, center } = useMemo(() => {
    const halfAngle = coverageHalfAngle(altitudeKm)
    const cap = buildSphericalCap(halfAngle, 72)

    // Orient the cap so its apex points from origin to (lat, lon).
    const target = latLonToVec3(lat, lon, 1).normalize()
    const quaternion = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      target,
    )
    cap.applyQuaternion(quaternion)

    const ring: number[] = []
    const segments = 96
    const ringRadius = EARTH_SCENE_RADIUS * Math.sin(halfAngle)
    const ringHeight = EARTH_SCENE_RADIUS * Math.cos(halfAngle)
    for (let i = 0; i <= segments; i++) {
      const t = (i / segments) * Math.PI * 2
      const v = new THREE.Vector3(
        ringRadius * Math.cos(t),
        ringHeight,
        ringRadius * Math.sin(t),
      ).applyQuaternion(quaternion)
      ring.push(v.x, v.y, v.z)
    }

    return {
      capGeom: cap,
      ringPositions: new Float32Array(ring),
      center: target.clone().multiplyScalar(EARTH_SCENE_RADIUS * 1.001),
    }
  }, [lat, lon, altitudeKm])

  const fillColor = accent ? "#7aa7e0" : "#8fb3d9"
  const ringColor = accent ? "#cfe1f5" : "#9bbfe2"

  return (
    <group>
      <mesh geometry={capGeom}>
        <meshBasicMaterial
          color={fillColor}
          transparent
          opacity={accent ? 0.22 : 0.11}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
      <lineLoop>
        <bufferGeometry attach="geometry">
          <bufferAttribute
            attach="attributes-position"
            args={[ringPositions, 3]}
            count={ringPositions.length / 3}
          />
        </bufferGeometry>
        <lineBasicMaterial
          color={ringColor}
          transparent
          opacity={accent ? 0.85 : 0.45}
        />
      </lineLoop>
      <mesh position={center}>
        <sphereGeometry args={[0.005, 8, 8]} />
        <meshBasicMaterial color={ringColor} />
      </mesh>
    </group>
  )
}

/**
 * Builds a spherical-cap mesh of radius EARTH_SCENE_RADIUS with its apex
 * along +Y. Uses concentric rings so the mesh curves along the sphere
 * rather than cutting through it.
 */
function buildSphericalCap(
  halfAngle: number,
  rings: number,
): THREE.BufferGeometry {
  const positions: number[] = []
  const indices: number[] = []
  const segments = 72
  const R = EARTH_SCENE_RADIUS * 1.002 // slight offset to avoid z-fighting

  positions.push(0, R, 0)
  for (let r = 1; r <= rings; r++) {
    const phi = (r / rings) * halfAngle
    const y = R * Math.cos(phi)
    const ringR = R * Math.sin(phi)
    for (let s = 0; s < segments; s++) {
      const theta = (s / segments) * Math.PI * 2
      positions.push(ringR * Math.cos(theta), y, ringR * Math.sin(theta))
    }
  }

  // Triangle fan for first ring
  for (let s = 0; s < segments; s++) {
    const a = 0
    const b = 1 + s
    const c = 1 + ((s + 1) % segments)
    indices.push(a, b, c)
  }
  // Strips for remaining rings
  for (let r = 1; r < rings; r++) {
    const start = 1 + (r - 1) * segments
    const next = 1 + r * segments
    for (let s = 0; s < segments; s++) {
      const sNext = (s + 1) % segments
      indices.push(start + s, next + s, next + sNext)
      indices.push(start + s, next + sNext, start + sNext)
    }
  }

  const geom = new THREE.BufferGeometry()
  geom.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  )
  geom.setIndex(indices)
  geom.computeVertexNormals()
  return geom
}
