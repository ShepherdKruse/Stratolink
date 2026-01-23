"use client"

import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { useEffect, useRef } from "react"

export function Hero() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const resizeCanvas = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resizeCanvas()
    window.addEventListener("resize", resizeCanvas)

    class WindPath {
      x: number
      y: number
      vx: number
      vy: number
      life: number
      maxLife: number

      constructor() {
        this.x = Math.random() * canvas.width
        this.y = Math.random() * canvas.height
        this.vx = (Math.random() - 0.5) * 0.5
        this.vy = (Math.random() - 0.5) * 0.3
        this.life = 0
        this.maxLife = 100 + Math.random() * 100
      }

      update() {
        this.x += this.vx
        this.y += this.vy
        this.life++

        if (this.x < 0 || this.x > canvas.width || this.y < 0 || this.y > canvas.height || this.life > this.maxLife) {
          this.x = Math.random() * canvas.width
          this.y = Math.random() * canvas.height
          this.life = 0
        }
      }

      draw(ctx: CanvasRenderingContext2D) {
        const opacity = Math.sin((this.life / this.maxLife) * Math.PI) * 0.03
        ctx.strokeStyle = `rgba(71, 85, 105, ${opacity})`
        ctx.lineWidth = 0.5
        ctx.beginPath()
        ctx.moveTo(this.x, this.y)
        ctx.lineTo(this.x - this.vx * 20, this.y - this.vy * 20)
        ctx.stroke()
      }
    }

    const paths: WindPath[] = []
    for (let i = 0; i < 40; i++) {
      paths.push(new WindPath())
    }

    let animationId: number
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      paths.forEach((path) => {
        path.update()
        path.draw(ctx)
      })
      animationId = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      window.removeEventListener("resize", resizeCanvas)
      cancelAnimationFrame(animationId)
    }
  }, [])

  return (
    <section className="relative overflow-hidden border-b bg-white">
      <div className="absolute inset-0 bg-gradient-to-b from-slate-50/40 via-white to-white" />

      <div className="relative mx-auto max-w-5xl px-6 py-32 sm:px-8 lg:py-40">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mb-12 flex justify-center">
            <Image
              src="/stratolink-icon.png"
              alt="Stratolink"
              width={544}
              height={256}
              className="h-32 w-auto opacity-90"
              priority
            />
          </div>

          <h1 className="text-balance text-4xl font-medium tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
            Stratospheric observation network
          </h1>

          <p className="mt-6 text-pretty text-lg font-light leading-relaxed text-slate-600 sm:text-xl">
            High-altitude atmospheric data collected via distributed balloon platforms
          </p>

          <div className="mt-14 flex flex-wrap items-center justify-center gap-4">
            <Button
              asChild
              size="lg"
              className="rounded-sm border border-primary/20 bg-primary px-8 py-6 text-base font-normal text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
            >
              <Link href="#contact">Request Access</Link>
            </Button>
            <Button
              asChild
              variant="ghost"
              size="lg"
              className="rounded-sm px-8 py-6 text-base font-normal text-foreground transition-all hover:bg-accent/50"
            >
              <Link href="#mission">Learn More</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}
