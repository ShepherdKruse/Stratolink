"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Play, Pause, RotateCcw } from "lucide-react"
import { WindCanvas } from "./wind-canvas"
import { generateMockWindField } from "@/lib/wind/mock"
import { generateMockTrajectories } from "@/lib/wind/trajectory"
import type { WindField, BalloonTrajectory } from "@/lib/wind/types"

interface WindTrajectoryCardProps {
  className?: string
  height?: number
  initialAltitudeBand?: "5km" | "15km"
  seed?: number
  useApi?: boolean
}

export function WindTrajectoryCard({
  className = "",
  height = 360,
  initialAltitudeBand = "15km",
  seed = 12345,
  useApi = false,
}: WindTrajectoryCardProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasWidth, setCanvasWidth] = useState(600)
  const [altitudeBand, setAltitudeBand] = useState<"5km" | "15km">(initialAltitudeBand)
  const [isPlaying, setIsPlaying] = useState(true)
  const [windField, setWindField] = useState<WindField | null>(null)
  const [trajectories, setTrajectories] = useState<BalloonTrajectory[]>([])
  const [hoveredTrajectory, setHoveredTrajectory] = useState<string | null>(null)

  // Responsive width
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setCanvasWidth(containerRef.current.offsetWidth)
      }
    }

    updateWidth()
    window.addEventListener("resize", updateWidth)
    return () => window.removeEventListener("resize", updateWidth)
  }, [])

  // Generate wind field and trajectories
  useEffect(() => {
    const field = generateMockWindField(altitudeBand, seed)
    setWindField(field)
    setTrajectories(generateMockTrajectories(field, 4))
  }, [altitudeBand, seed])

  const handleReset = () => {
    const field = generateMockWindField(altitudeBand, seed + Date.now())
    setWindField(field)
    setTrajectories(generateMockTrajectories(field, 4))
  }

  if (!windField) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center" style={{ height }}>
          <div className="text-sm text-muted-foreground">Loading wind field...</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-normal">Wind Field Visualization</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Stratospheric wind patterns and balloon trajectory integration
            </p>
          </div>
          <Badge variant="outline" className="text-xs font-normal">
            {trajectories.filter((t) => t.status === "active").length} Active
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsPlaying(!isPlaying)} className="h-8 w-8 p-0">
              {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </Button>
            <Button variant="outline" size="sm" onClick={handleReset} className="h-8 w-8 p-0 bg-transparent">
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>

          <Select value={altitudeBand} onValueChange={(v) => setAltitudeBand(v as "5km" | "15km")}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5km">5 km altitude</SelectItem>
              <SelectItem value="15km">15 km altitude</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Canvas */}
        <div ref={containerRef} className="w-full overflow-hidden rounded-sm border">
          <WindCanvas
            windField={windField}
            trajectories={trajectories}
            width={canvasWidth}
            height={height}
            isPlaying={isPlaying}
            hoveredTrajectory={hoveredTrajectory}
            onTrajectoryHover={setHoveredTrajectory}
          />
        </div>

        {/* Legend */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full bg-blue-600" />
              <span>Active trajectory</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full bg-slate-400" />
              <span>Predicted</span>
            </div>
          </div>
          <span>
            {windField.bounds.latMin}°N–{windField.bounds.latMax}°N, {Math.abs(windField.bounds.lonMax)}°W–
            {Math.abs(windField.bounds.lonMin)}°W
          </span>
        </div>

        {/* Trajectory info on hover */}
        {hoveredTrajectory && (
          <div className="rounded-sm border bg-slate-50 p-3 text-sm">
            {trajectories
              .filter((t) => t.balloonId === hoveredTrajectory)
              .map((t) => (
                <div key={t.balloonId} className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{t.balloonId}</span>
                    <span className="ml-2 text-muted-foreground">from {t.launchSite}</span>
                  </div>
                  <Badge variant={t.status === "active" ? "default" : "secondary"} className="text-xs">
                    {t.status}
                  </Badge>
                </div>
              ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
