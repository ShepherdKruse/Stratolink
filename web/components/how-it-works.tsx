"use client"

import { useEffect, useRef, useState } from "react"

export function HowItWorks() {
  const [isVisible, setIsVisible] = useState(false)
  const sectionRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
        }
      },
      { threshold: 0.1 },
    )

    if (sectionRef.current) {
      observer.observe(sectionRef.current)
    }

    return () => observer.disconnect()
  }, [])

  const steps = [
    {
      number: "01",
      title: "Balloon Deployment",
      description:
        "Instrumented pico balloons are released from designated launch sites and ascend to operational altitude.",
    },
    {
      number: "02",
      title: "Stratospheric Drift",
      description:
        "Balloons enter predictable wind currents in the stratosphere, collecting continuous environmental measurements.",
    },
    {
      number: "03",
      title: "Telemetry & Tracking",
      description:
        "Sensor data and position information are transmitted to ground stations via radio telemetry at regular intervals.",
    },
    {
      number: "04",
      title: "Data Validation",
      description:
        "Observations undergo quality control, calibration checks, and are published in standardized formats for research use.",
    },
  ]

  return (
    <section ref={sectionRef} id="how-it-works" className="border-b py-32 sm:py-40">
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div
          className={`mx-auto max-w-2xl transition-all duration-1000 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          <h2 className="text-4xl font-light tracking-tight text-foreground sm:text-5xl">How It Works</h2>
          <p className="mt-8 text-lg leading-relaxed text-muted-foreground">
            Our observation system uses long-duration balloons that drift with stratospheric wind currents. Each balloon
            carries calibrated instruments that measure temperature, pressure, position, and other environmental
            parameters. Data is transmitted in real-time and archived for research access.
          </p>
        </div>

        <div
          className={`mt-20 rounded-sm border bg-card p-16 shadow-sm transition-all duration-1000 delay-300 hover:shadow-md ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          <div className="mx-auto max-w-3xl">
            <svg viewBox="0 0 800 300" className="w-full text-muted-foreground" xmlns="http://www.w3.org/2000/svg">
              {/* Ground */}
              <line x1="0" y1="280" x2="800" y2="280" stroke="currentColor" strokeWidth="1" opacity="0.3" />
              <text x="20" y="295" fontSize="12" fill="currentColor" opacity="0.5" fontFamily="sans-serif">
                Ground Level
              </text>

              {/* Stratosphere indicator */}
              <line
                x1="0"
                y1="80"
                x2="800"
                y2="80"
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray="4 4"
                opacity="0.2"
              />
              <text x="20" y="70" fontSize="12" fill="currentColor" opacity="0.5" fontFamily="sans-serif">
                Stratosphere
              </text>

              {/* Balloons */}
              <circle cx="150" cy="120" r="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <line x1="150" y1="128" x2="150" y2="160" stroke="currentColor" strokeWidth="1" />

              <circle cx="400" cy="100" r="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <line x1="400" y1="108" x2="400" y2="140" stroke="currentColor" strokeWidth="1" />

              <circle cx="650" cy="130" r="8" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <line x1="650" y1="138" x2="650" y2="170" stroke="currentColor" strokeWidth="1" />

              {/* Communication lines */}
              <line
                x1="158"
                y1="120"
                x2="392"
                y2="100"
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray="3 3"
                opacity="0.4"
              />
              <line
                x1="408"
                y1="100"
                x2="642"
                y2="130"
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray="3 3"
                opacity="0.4"
              />

              {/* Ground station */}
              <rect x="380" y="250" width="40" height="30" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <line x1="400" y1="250" x2="400" y2="230" stroke="currentColor" strokeWidth="1" />
              <line x1="390" y1="230" x2="410" y2="230" stroke="currentColor" strokeWidth="1.5" />

              {/* Connection to ground */}
              <line
                x1="400"
                y1="140"
                x2="400"
                y2="230"
                stroke="currentColor"
                strokeWidth="1"
                strokeDasharray="3 3"
                opacity="0.4"
              />

              {/* Labels */}
              <text x="120" y="200" fontSize="11" fill="currentColor" opacity="0.6" fontFamily="sans-serif">
                Sensor Package
              </text>
              <text x="345" y="295" fontSize="11" fill="currentColor" opacity="0.6" fontFamily="sans-serif">
                Ground Station
              </text>
            </svg>
          </div>
        </div>

        <div
          className={`mt-20 grid gap-10 sm:grid-cols-2 lg:grid-cols-4 transition-all duration-1000 delay-500 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          {steps.map((step, index) => (
            <div key={step.number} className="group" style={{ transitionDelay: `${500 + index * 100}ms` }}>
              <div className="text-sm font-light text-muted-foreground/60 transition-colors group-hover:text-muted-foreground">
                {step.number}
              </div>
              <h3 className="mt-4 text-base font-normal text-foreground">{step.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
