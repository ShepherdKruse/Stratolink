"use client"

import { useEffect, useRef, useState } from "react"

type Stop = {
  id: string
  title: string
  subtitle: string
  detail: string
  icon: (active: boolean) => React.ReactNode
}

const STOPS: Stop[] = [
  {
    id: "balloon",
    title: "Balloon wakes",
    subtitle: "STM32WLE5 + sensors",
    detail:
      "RTC alarm or freefall interrupt brings the MCU out of STOP2 deep sleep. GPS fixes, sensors sample, power tier is decided.",
    icon: (active) => (
      <svg viewBox="0 0 32 32" fill="none" className="h-6 w-6">
        <ellipse
          cx="16"
          cy="12"
          rx="7"
          ry="9"
          stroke="currentColor"
          strokeWidth={active ? 1.8 : 1.2}
          fill={active ? "currentColor" : "none"}
          fillOpacity={active ? 0.1 : 0}
        />
        <path
          d="M16 21 L16 28"
          stroke="currentColor"
          strokeWidth="1"
        />
        <rect
          x="12"
          y="28"
          width="8"
          height="2"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    id: "lora",
    title: "LoRaWAN uplink",
    subtitle: "40 bytes · sub-GHz",
    detail:
      "LoRaWAN-protected frame transmitted at SF9/125 kHz on US915 sub-band 2 (or regional equivalent). Unconfirmed; no retry.",
    icon: (active) => (
      <svg viewBox="0 0 32 32" fill="none" className="h-6 w-6">
        <path
          d="M16 22 Q10 16 16 10 Q22 16 16 22"
          stroke="currentColor"
          strokeWidth={active ? 1.8 : 1.2}
          strokeLinecap="round"
        />
        <path
          d="M16 26 Q6 16 16 6 Q26 16 16 26"
          stroke="currentColor"
          strokeWidth={active ? 1.4 : 0.9}
          strokeOpacity="0.6"
          strokeLinecap="round"
        />
        <circle cx="16" cy="16" r="1.5" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: "gateway",
    title: "TTN gateway",
    subtitle: "Community relay",
    detail:
      "Any in-range LoRaWAN gateway forwards the frame up to The Things Network. Multiple gateways add receive diversity without coordination.",
    icon: (active) => (
      <svg viewBox="0 0 32 32" fill="none" className="h-6 w-6">
        <path
          d="M16 4 L10 12 L22 12 Z"
          stroke="currentColor"
          strokeWidth={active ? 1.8 : 1.2}
          strokeLinejoin="round"
          fill={active ? "currentColor" : "none"}
          fillOpacity={active ? 0.08 : 0}
        />
        <line
          x1="16"
          y1="12"
          x2="16"
          y2="26"
          stroke="currentColor"
          strokeWidth="1"
        />
        <line x1="10" y1="26" x2="22" y2="26" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    ),
  },
  {
    id: "webhook",
    title: "Webhook + parser",
    subtitle: "/api/ttn-webhook",
    detail:
      "A Next.js route decodes the big-endian payload (lat/lon ×1e7, pressure ×0.1 hPa, …) and inserts a row into Supabase.",
    icon: (active) => (
      <svg viewBox="0 0 32 32" fill="none" className="h-6 w-6">
        <path
          d="M6 16 L12 10 L20 22 L26 16"
          stroke="currentColor"
          strokeWidth={active ? 1.8 : 1.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="6" cy="16" r="2" fill="currentColor" />
        <circle cx="26" cy="16" r="2" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: "dashboard",
    title: "Mission Control",
    subtitle: "Realtime map + API",
    detail:
      "The dashboard subscribes to Supabase realtime, plotting positions on Mapbox and streaming sensor charts.",
    icon: (active) => (
      <svg viewBox="0 0 32 32" fill="none" className="h-6 w-6">
        <rect
          x="5"
          y="7"
          width="22"
          height="16"
          rx="1"
          stroke="currentColor"
          strokeWidth={active ? 1.8 : 1.2}
          fill={active ? "currentColor" : "none"}
          fillOpacity={active ? 0.08 : 0}
        />
        <line x1="5" y1="12" x2="27" y2="12" stroke="currentColor" strokeWidth="1" />
        <circle cx="8" cy="9.5" r="0.8" fill="currentColor" />
        <circle cx="11" cy="9.5" r="0.8" fill="currentColor" />
        <path
          d="M9 18 L13 15 L17 19 L23 14"
          stroke="currentColor"
          strokeWidth="1"
          fill="none"
        />
      </svg>
    ),
  },
]

export function DataFlowDiagram() {
  const [activeIdx, setActiveIdx] = useState(0)
  const [userHovered, setUserHovered] = useState<number | null>(null)
  const cycleRef = useRef<number | null>(null)

  useEffect(() => {
    cycleRef.current = window.setInterval(() => {
      setActiveIdx((prev) => (prev + 1) % STOPS.length)
    }, 2200)
    return () => {
      if (cycleRef.current) window.clearInterval(cycleRef.current)
    }
  }, [])

  const displayIdx = userHovered ?? activeIdx
  const displayed = STOPS[displayIdx]

  return (
    <div className="rounded-sm border border-border bg-card p-6 shadow-sm sm:p-10">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Data Path
          </div>
          <h3 className="mt-3 text-2xl font-light tracking-tight text-foreground sm:text-3xl">
            Stratosphere to browser in one minute.
          </h3>
        </div>
        <div className="hidden text-right text-[11px] text-muted-foreground sm:block">
          <div>Packet travelling…</div>
          <div className="mt-0.5 font-mono">
            Frame {String(activeIdx + 1).padStart(2, "0")}
            /{String(STOPS.length).padStart(2, "0")}
          </div>
        </div>
      </div>

      <div className="relative mt-10">
        {/* Connector line */}
        <div className="absolute left-0 right-0 top-[34px] hidden h-px bg-border sm:block" />
        {/* Progress overlay */}
        <div
          className="absolute left-0 top-[34px] hidden h-px bg-foreground/70 transition-all duration-700 ease-out sm:block"
          style={{
            width: `${(displayIdx / (STOPS.length - 1)) * 100}%`,
          }}
        />

        <ol className="relative grid gap-8 sm:grid-cols-5 sm:gap-4">
          {STOPS.map((stop, idx) => {
            const isActive = idx === displayIdx
            const isPast = idx < displayIdx
            return (
              <li
                key={stop.id}
                onMouseEnter={() => setUserHovered(idx)}
                onMouseLeave={() => setUserHovered(null)}
                onFocus={() => setUserHovered(idx)}
                onBlur={() => setUserHovered(null)}
                className="group relative flex flex-col items-start sm:items-center"
              >
                <button
                  type="button"
                  onClick={() => setUserHovered(idx)}
                  className={`relative z-10 flex h-[68px] w-[68px] items-center justify-center rounded-full border bg-background transition-all duration-300 ${
                    isActive
                      ? "border-foreground text-foreground shadow-sm"
                      : isPast
                        ? "border-foreground/30 text-foreground/70"
                        : "border-border text-muted-foreground"
                  }`}
                  aria-label={stop.title}
                >
                  {stop.icon(isActive)}
                  {isActive && (
                    <span className="pointer-events-none absolute inset-[-6px] rounded-full border border-foreground/20 motion-safe:animate-ping" />
                  )}
                </button>
                <div
                  className={`mt-4 text-xs font-light leading-snug sm:mt-5 sm:text-center ${
                    isActive ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  <div className="font-normal">{stop.title}</div>
                  <div className="mt-0.5 font-mono text-[10px] text-muted-foreground/80">
                    {stop.subtitle}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </div>

      <div className="mt-10 rounded-sm border border-border bg-muted/40 p-6">
        <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          {displayed.subtitle}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-foreground/80">
          {displayed.detail}
        </p>
      </div>
    </div>
  )
}
