"use client"

import type React from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useEffect, useRef, useState } from "react"
import { ArrowRight, Mail } from "lucide-react"
import { subscribeLaunchUpdates } from "@/app/actions/launch-updates"

export function Hero() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [email, setEmail] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setStatus(null)

    const result = await subscribeLaunchUpdates(email)

    if (result.success) {
      setStatus({ type: "success", message: "Thanks — we'll keep you posted on launches." })
      setEmail("")
    } else {
      setStatus({ type: "error", message: result.error || "Something went wrong." })
    }

    setIsSubmitting(false)
  }

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

          <div className="mx-auto mt-10 w-full max-w-md">
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl ring-1 ring-slate-100">
              <div className="h-1 w-full bg-gradient-to-r from-primary/70 via-primary to-primary/70" />
              <form
                onSubmit={handleSubmit}
                className="px-5 py-5 text-left sm:px-6 sm:py-6"
                aria-label="Get launch updates by email"
              >
                <div className="flex items-center justify-center gap-2 text-center">
                  <Mail className="h-4 w-4 text-primary" aria-hidden />
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                    Get launch updates
                  </p>
                </div>
                <p className="mt-2 text-center text-sm leading-relaxed text-slate-600">
                  Be first to hear when we fly. One email, no spam.
                </p>

                <div className="mt-5 flex w-full flex-col gap-2 sm:flex-row sm:gap-2.5">
                  <label htmlFor="hero-launch-email" className="sr-only">
                    Email address
                  </label>
                  <div className="relative flex-1">
                    <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
                    <Input
                      id="hero-launch-email"
                      type="email"
                      name="email"
                      inputMode="email"
                      autoComplete="email"
                      required
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="h-12 w-full rounded-md border-slate-300 bg-white pl-10 pr-4 text-base shadow-sm placeholder:text-slate-400 focus-visible:border-primary md:text-base"
                    />
                  </div>
                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="group h-12 w-full shrink-0 rounded-md bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-md transition-all hover:bg-primary/90 hover:shadow-lg disabled:opacity-60 sm:w-auto"
                  >
                    <span>{isSubmitting ? "Sending…" : "Notify me"}</span>
                    {!isSubmitting && (
                      <ArrowRight
                        className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-0.5"
                        aria-hidden
                      />
                    )}
                  </Button>
                </div>

                {status && (
                  <p
                    role="status"
                    className={`mt-4 text-center text-sm ${
                      status.type === "success" ? "text-emerald-700" : "text-destructive"
                    }`}
                  >
                    {status.message}
                  </p>
                )}
              </form>
            </div>
          </div>

          <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
            <Button
              asChild
              size="lg"
              className="rounded-sm border border-primary/20 bg-primary px-8 py-6 text-base font-normal text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
            >
              <Link href="#contact" className="scroll-smooth">Request Access</Link>
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
