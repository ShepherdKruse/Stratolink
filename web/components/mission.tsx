"use client"

import { Card } from "@/components/ui/card"
import { useEffect, useRef, useState } from "react"

export function Mission() {
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

  const pillars = [
    {
      title: "Expand upper-air coverage",
      description:
        "Deploy cost-effective sensor networks across undersampled regions to increase atmospheric observation density.",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z"
          />
        </svg>
      ),
    },
    {
      title: "Reduce cost per observation",
      description:
        "Leverage pico balloon technology to achieve observations at a fraction of traditional radiosonde costs.",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"
          />
        </svg>
      ),
    },
    {
      title: "Publish open, well-documented datasets",
      description:
        "Provide validated, calibrated data with complete metadata for research, education, and operational use.",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
          />
        </svg>
      ),
    },
  ]

  return (
    <section ref={sectionRef} id="mission" className="border-b py-32 sm:py-40">
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div
          className={`mx-auto max-w-2xl transition-all duration-1000 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          <h2 className="text-4xl font-light tracking-tight text-foreground sm:text-5xl">Mission</h2>
          <div className="mt-10 space-y-6 text-lg leading-relaxed text-muted-foreground">
            <p>
              Stratolink operates a stratospheric observation network designed to address gaps in atmospheric data
              collection. Our platform provides high-resolution wind measurements, temperature profiles, and
              environmental monitoring across regions with limited traditional infrastructure.
            </p>
            <p>
              Using long-duration pico balloons equipped with calibrated sensors, we collect continuous atmospheric data
              between 10-20 km altitude. This altitude band—above weather systems and below satellites—offers unique
              insights into stratospheric dynamics and long-range transport patterns.
            </p>
            <p>
              Our datasets are made freely available to researchers, educators, and institutions. We maintain rigorous
              documentation standards, including sensor specifications, calibration protocols, and quality control
              procedures, ensuring our data meets the requirements of peer-reviewed research.
            </p>
          </div>
        </div>

        <div
          className={`mt-20 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 transition-all duration-1000 delay-300 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          {pillars.map((pillar, index) => (
            <Card
              key={pillar.title}
              className="group rounded-sm border border-border bg-card p-8 shadow-sm transition-all duration-300 hover:border-foreground/20 hover:shadow-md"
              style={{ transitionDelay: `${index * 100}ms` }}
            >
              <div className="text-muted-foreground transition-colors group-hover:text-foreground">{pillar.icon}</div>
              <h3 className="mt-5 text-lg font-normal text-foreground">{pillar.title}</h3>
              <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{pillar.description}</p>
            </Card>
          ))}
        </div>
      </div>

      <div className="mx-auto mt-32 max-w-5xl">
        <div className="grid grid-cols-12 gap-px border-t border-border/50">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-px bg-border/30" />
          ))}
        </div>
      </div>
    </section>
  )
}
