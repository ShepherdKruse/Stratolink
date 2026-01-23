"use client"

import type React from "react"

import { useEffect, useRef, useCallback } from "react"
import type { WindField, BalloonTrajectory, Particle } from "@/lib/wind/types"
import { latLonToCanvas, windSpeed, interpolateWind } from "@/lib/wind/utils"

interface WindCanvasProps {
  windField: WindField
  trajectories: BalloonTrajectory[]
  width: number
  height: number
  isPlaying: boolean
  showParticles?: boolean
  hoveredTrajectory?: string | null
  onTrajectoryHover?: (id: string | null) => void
}

export function WindCanvas({
  windField,
  trajectories,
  width,
  height,
  isPlaying,
  showParticles = true,
  hoveredTrajectory,
  onTrajectoryHover,
}: WindCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const animationRef = useRef<number>()

  const PARTICLE_COUNT = 800
  const PARTICLE_LINE_WIDTH = 0.8
  const PARTICLE_MAX_AGE = 80

  // Initialize particles
  useEffect(() => {
    particlesRef.current = Array.from({ length: PARTICLE_COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      age: Math.floor(Math.random() * PARTICLE_MAX_AGE),
      maxAge: PARTICLE_MAX_AGE + Math.floor(Math.random() * 20),
      speed: 0,
    }))
  }, [width, height])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Clear with slight fade for trail effect
    ctx.fillStyle = "rgba(248, 250, 252, 0.15)"
    ctx.fillRect(0, 0, width, height)

    // Draw grid lines
    ctx.strokeStyle = "rgba(148, 163, 184, 0.15)"
    ctx.lineWidth = 0.5

    const gridSpacing = 40
    for (let x = 0; x < width; x += gridSpacing) {
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, height)
      ctx.stroke()
    }
    for (let y = 0; y < height; y += gridSpacing) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(width, y)
      ctx.stroke()
    }

    // Update and draw particles
    if (showParticles && isPlaying) {
      particlesRef.current.forEach((particle) => {
        const { lat, lon } = canvasToLatLon(particle.x, particle.y)
        const wind = interpolateWind(lat, lon, windField.grid, windField.bounds, windField.gridResolution)

        const speed = windSpeed(wind)
        particle.speed = speed

        // Normalize wind for movement
        const scale = 0.3
        const dx = wind.u * scale
        const dy = -wind.v * scale

        const oldX = particle.x
        const oldY = particle.y

        particle.x += dx
        particle.y += dy
        particle.age++

        // Reset if out of bounds or too old
        if (
          particle.x < 0 ||
          particle.x > width ||
          particle.y < 0 ||
          particle.y > height ||
          particle.age > particle.maxAge
        ) {
          particle.x = Math.random() * width
          particle.y = Math.random() * height
          particle.age = 0
        } else {
          // Draw particle trail
          const alpha = Math.max(0, 1 - particle.age / particle.maxAge) * 0.6
          const hue = 200 + (speed / 25) * 30
          ctx.strokeStyle = `hsla(${hue}, 60%, 50%, ${alpha})`
          ctx.lineWidth = PARTICLE_LINE_WIDTH
          ctx.beginPath()
          ctx.moveTo(oldX, oldY)
          ctx.lineTo(particle.x, particle.y)
          ctx.stroke()
        }
      })
    }

    // Draw trajectories
    trajectories.forEach((trajectory) => {
      const isHovered = hoveredTrajectory === trajectory.balloonId
      const isActive = trajectory.status === "active"

      ctx.strokeStyle = isHovered
        ? "rgba(37, 99, 235, 0.9)"
        : isActive
          ? "rgba(37, 99, 235, 0.7)"
          : "rgba(100, 116, 139, 0.5)"
      ctx.lineWidth = isHovered ? 3 : isActive ? 2 : 1.5

      ctx.beginPath()
      trajectory.points.forEach((point, idx) => {
        const { x, y } = latLonToCanvas(point.lat, point.lon, windField.bounds, width, height)

        if (idx === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      })
      ctx.stroke()

      // Draw start point
      if (trajectory.points.length > 0) {
        const start = trajectory.points[0]
        const { x, y } = latLonToCanvas(start.lat, start.lon, windField.bounds, width, height)

        ctx.fillStyle = isActive ? "#2563eb" : "#64748b"
        ctx.beginPath()
        ctx.arc(x, y, isHovered ? 6 : 4, 0, Math.PI * 2)
        ctx.fill()

        // Label
        ctx.fillStyle = "#334155"
        ctx.font = "11px system-ui, sans-serif"
        ctx.fillText(trajectory.balloonId, x + 8, y + 4)
      }
    })

    if (isPlaying) {
      animationRef.current = requestAnimationFrame(draw)
    }
  }, [windField, trajectories, width, height, isPlaying, showParticles, hoveredTrajectory])

  // Helper function for particle canvas coordinates
  function canvasToLatLon(x: number, y: number) {
    const { bounds } = windField
    const lon = (x / width) * (bounds.lonMax - bounds.lonMin) + bounds.lonMin
    const lat = bounds.latMax - (y / height) * (bounds.latMax - bounds.latMin)
    return { lat, lon }
  }

  useEffect(() => {
    draw()
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [draw])

  // Handle mouse move for trajectory hover
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onTrajectoryHover) return

      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return

      const x = e.clientX - rect.left
      const y = e.clientY - rect.top

      // Check if near any trajectory
      let foundId: string | null = null
      trajectories.forEach((trajectory) => {
        trajectory.points.forEach((point) => {
          const pos = latLonToCanvas(point.lat, point.lon, windField.bounds, width, height)
          const dist = Math.sqrt((pos.x - x) ** 2 + (pos.y - y) ** 2)
          if (dist < 10) {
            foundId = trajectory.balloonId
          }
        })
      })

      onTrajectoryHover(foundId)
    },
    [trajectories, windField.bounds, width, height, onTrajectoryHover],
  )

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className="rounded-sm bg-slate-50"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => onTrajectoryHover?.(null)}
    />
  )
}
