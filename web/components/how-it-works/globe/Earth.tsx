"use client"

import { useMemo } from "react"
import * as THREE from "three"
import { EARTH_SCENE_RADIUS } from "./utils"

/**
 * Stylised Earth: a dark, faintly-shaded sphere with a graticule ring
 * and a soft atmospheric halo. Intentionally abstract — the story is
 * the balloons, so Earth stays quiet.
 */
export function Earth() {
  const graticule = useMemo(() => buildGraticule(), [])
  const atmosphereGeom = useMemo(
    () => new THREE.SphereGeometry(EARTH_SCENE_RADIUS * 1.08, 96, 96),
    [],
  )
  const sphereGeom = useMemo(
    () => new THREE.SphereGeometry(EARTH_SCENE_RADIUS, 96, 96),
    [],
  )

  return (
    <group>
      <mesh geometry={sphereGeom}>
        <meshStandardMaterial
          color="#0b1220"
          roughness={0.95}
          metalness={0.05}
        />
      </mesh>

      <lineSegments geometry={graticule}>
        <lineBasicMaterial
          color="#4a6477"
          transparent
          opacity={0.18}
        />
      </lineSegments>

      <mesh geometry={atmosphereGeom}>
        <shaderMaterial
          transparent
          side={THREE.BackSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          uniforms={{
            glowColor: { value: new THREE.Color("#4c7ea8") },
            power: { value: 2.6 },
            intensity: { value: 0.9 },
          }}
          vertexShader={atmosphereVertex}
          fragmentShader={atmosphereFragment}
        />
      </mesh>
    </group>
  )
}

const atmosphereVertex = /* glsl */ `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const atmosphereFragment = /* glsl */ `
  varying vec3 vNormal;
  uniform vec3 glowColor;
  uniform float power;
  uniform float intensity;
  void main() {
    float rim = pow(1.0 - abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), power);
    gl_FragColor = vec4(glowColor, rim * intensity);
  }
`

function buildGraticule(): THREE.BufferGeometry {
  const positions: number[] = []
  const R = EARTH_SCENE_RADIUS * 1.001

  const pushArc = (
    toPoint: (t: number) => [number, number, number],
    segments: number,
  ) => {
    for (let i = 0; i < segments; i++) {
      const a = i / segments
      const b = (i + 1) / segments
      const p1 = toPoint(a)
      const p2 = toPoint(b)
      positions.push(...p1, ...p2)
    }
  }

  // Parallels every 30°
  for (let lat = -60; lat <= 60; lat += 30) {
    const phi = (90 - lat) * (Math.PI / 180)
    const ringR = R * Math.sin(phi)
    const y = R * Math.cos(phi)
    pushArc((t) => {
      const theta = t * 2 * Math.PI
      return [ringR * Math.cos(theta), y, ringR * Math.sin(theta)]
    }, 128)
  }

  // Meridians every 30°
  for (let lon = 0; lon < 360; lon += 30) {
    const theta = (lon + 180) * (Math.PI / 180)
    pushArc((t) => {
      const phi = t * Math.PI
      const x = -R * Math.sin(phi) * Math.cos(theta)
      const z = R * Math.sin(phi) * Math.sin(theta)
      const y = R * Math.cos(phi)
      return [x, y, z]
    }, 96)
  }

  const geom = new THREE.BufferGeometry()
  geom.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  )
  return geom
}
