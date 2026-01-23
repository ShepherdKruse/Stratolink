"use client"

import { useRef, useEffect } from "react"

function AltitudeSchematic() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height
    const centerX = width / 2
    const centerY = height / 2

    let frame = 0
    let animationId: number

    const draw = () => {
      ctx.clearRect(0, 0, width, height)

      // Draw atmospheric layers (horizontal bands)
      const layerColors = [
        "rgba(180, 200, 220, 0.15)",
        "rgba(160, 185, 210, 0.12)",
        "rgba(140, 170, 200, 0.1)",
        "rgba(120, 155, 190, 0.08)",
      ]

      const layerHeight = height / 5
      layerColors.forEach((color, i) => {
        ctx.fillStyle = color
        ctx.fillRect(0, height - (i + 1) * layerHeight, width, layerHeight)
      })

      // Draw altitude labels
      ctx.fillStyle = "rgba(100, 116, 139, 0.5)"
      ctx.font = "11px Inter, system-ui, sans-serif"
      ctx.textAlign = "right"
      const altitudes = ["5 km", "10 km", "15 km", "20 km"]
      altitudes.forEach((alt, i) => {
        ctx.fillText(alt, width - 12, height - (i + 1) * layerHeight - 8)
      })

      // Draw horizontal wind indicators
      ctx.strokeStyle = "rgba(100, 116, 139, 0.2)"
      ctx.lineWidth = 1
      for (let i = 1; i <= 4; i++) {
        const y = height - i * layerHeight
        ctx.beginPath()
        ctx.setLineDash([4, 8])
        ctx.moveTo(20, y)
        ctx.lineTo(width - 60, y)
        ctx.stroke()
        ctx.setLineDash([])
      }

      // Balloon vertical position oscillates to show altitude control
      const oscillation = Math.sin(frame * 0.015) * 40
      const balloonY = centerY - 20 + oscillation

      // Draw vertical control arrows
      const arrowAlpha = 0.4 + Math.sin(frame * 0.03) * 0.2

      // Up arrow
      ctx.fillStyle = `rgba(55, 65, 81, ${arrowAlpha})`
      ctx.beginPath()
      ctx.moveTo(centerX, balloonY - 70)
      ctx.lineTo(centerX - 8, balloonY - 55)
      ctx.lineTo(centerX + 8, balloonY - 55)
      ctx.closePath()
      ctx.fill()

      // Down arrow
      ctx.fillStyle = `rgba(55, 65, 81, ${arrowAlpha * 0.7})`
      ctx.beginPath()
      ctx.moveTo(centerX, balloonY + 70)
      ctx.lineTo(centerX - 8, balloonY + 55)
      ctx.lineTo(centerX + 8, balloonY + 55)
      ctx.closePath()
      ctx.fill()

      // Draw control mode labels
      ctx.fillStyle = "rgba(55, 65, 81, 0.6)"
      ctx.font = "10px Inter, system-ui, sans-serif"
      ctx.textAlign = "center"
      ctx.fillText("ASCENT MODE", centerX, balloonY - 78)
      ctx.fillText("DESCENT MODE", centerX, balloonY + 82)

      // Draw balloon envelope (simple ellipse)
      ctx.fillStyle = "rgba(55, 65, 81, 0.08)"
      ctx.strokeStyle = "rgba(55, 65, 81, 0.6)"
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.ellipse(centerX, balloonY, 28, 22, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()

      // Draw payload line
      ctx.strokeStyle = "rgba(55, 65, 81, 0.4)"
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(centerX, balloonY + 22)
      ctx.lineTo(centerX, balloonY + 42)
      ctx.stroke()

      // Draw payload box
      ctx.fillStyle = "rgba(55, 65, 81, 0.15)"
      ctx.strokeStyle = "rgba(55, 65, 81, 0.6)"
      ctx.lineWidth = 1.5
      ctx.fillRect(centerX - 10, balloonY + 42, 20, 14)
      ctx.strokeRect(centerX - 10, balloonY + 42, 20, 14)

      // Draw active control band indicator
      const bandY = balloonY + 8
      ctx.strokeStyle = "rgba(55, 65, 81, 0.8)"
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(centerX - 24, bandY)
      ctx.lineTo(centerX + 24, bandY)
      ctx.stroke()

      // Control band label
      ctx.fillStyle = "rgba(55, 65, 81, 0.7)"
      ctx.font = "9px Inter, system-ui, sans-serif"
      ctx.textAlign = "left"
      ctx.fillText("ACTIVE CONTROL", centerX + 32, bandY + 3)

      // Draw thermal state indicators
      const stateA = oscillation > 0
      ctx.fillStyle = stateA ? "rgba(55, 65, 81, 0.7)" : "rgba(55, 65, 81, 0.25)"
      ctx.beginPath()
      ctx.arc(centerX - 50, balloonY - 30, 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = "rgba(55, 65, 81, 0.5)"
      ctx.font = "9px Inter, system-ui, sans-serif"
      ctx.textAlign = "center"
      ctx.fillText("STATE A", centerX - 50, balloonY - 40)

      ctx.fillStyle = !stateA ? "rgba(55, 65, 81, 0.7)" : "rgba(55, 65, 81, 0.25)"
      ctx.beginPath()
      ctx.arc(centerX + 50, balloonY + 30, 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = "rgba(55, 65, 81, 0.5)"
      ctx.fillText("STATE B", centerX + 50, balloonY + 45)

      frame++
      animationId = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(animationId)
    }
  }, [])

  return <canvas ref={canvasRef} className="w-full h-full" style={{ width: "100%", height: "100%" }} />
}

export function AltitudeControl() {
  const specs = [
    { label: "Total control system mass", value: "< 15 g" },
    { label: "Control method", value: "Passive / electronically commanded" },
    { label: "Energy source", value: "Ambient environmental energy" },
    { label: "Control authority", value: "Layer selection and drift shaping" },
    { label: "Operational regime", value: "Troposphere → lower stratosphere" },
  ]

  return (
    <section id="altitude-control" className="py-32 bg-background">
      <div className="max-w-6xl mx-auto px-6">
        {/* Section header */}
        <div className="mb-16">
          <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase mb-4">
            Technical Capability
          </p>
          <h2 className="text-3xl md:text-4xl font-light text-foreground tracking-tight mb-4">
            Active Altitude Control at Pico Scale
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl font-light">
            Autonomous vertical control for stratospheric balloons with a total payload mass under 15 grams.
          </p>
        </div>

        {/* Two-column layout */}
        <div className="grid lg:grid-cols-2 gap-16 items-start">
          {/* Left column: text + callouts */}
          <div className="space-y-10">
            <div className="space-y-6">
              <p className="text-foreground/80 leading-relaxed">
                These pico balloons are not passive drifters. They actively modulate altitude to select atmospheric
                layers, biasing vertical motion to shape drift trajectories. Control is achieved through thermally
                mediated mechanisms—without propulsion, pumps, or ballast.
              </p>
              <p className="text-foreground/80 leading-relaxed">
                The system operates within an extreme mass and power envelope, enabling controlled interaction with wind
                shear and vertical transport regimes previously inaccessible to pico-scale platforms.
              </p>
            </div>

            {/* Technical specifications */}
            <div className="border border-border rounded-sm overflow-hidden">
              <div className="bg-secondary/50 px-5 py-3 border-b border-border">
                <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
                  System Specifications
                </p>
              </div>
              <div className="divide-y divide-border">
                {specs.map((spec, index) => (
                  <div key={index} className="px-5 py-4 flex justify-between items-start gap-4">
                    <span className="text-sm text-muted-foreground">{spec.label}</span>
                    <span className="text-sm text-foreground font-medium text-right">{spec.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Credibility line */}
            <p className="text-sm text-muted-foreground italic border-l-2 border-border pl-4">
              This capability enables controlled interaction with wind shear and vertical transport regimes previously
              inaccessible to pico-scale platforms.
            </p>
          </div>

          {/* Right column: schematic visualization */}
          <div className="lg:sticky lg:top-32">
            <div className="bg-secondary/30 border border-border rounded-sm p-6">
              <div className="aspect-square w-full max-w-md mx-auto">
                <AltitudeSchematic />
              </div>
              <p className="text-xs text-muted-foreground text-center mt-4 tracking-wide">
                Schematic: Active altitude control via thermal state modulation
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
