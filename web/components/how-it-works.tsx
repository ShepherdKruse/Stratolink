"use client"

import { useEffect, useRef, useState } from "react"
import { AltitudeScale } from "./how-it-works/AltitudeScale"
import { SingleBalloonScene } from "./how-it-works/SingleBalloonScene"
import { DataFlowDiagram } from "./how-it-works/DataFlowDiagram"
import { PacketAnatomy } from "./how-it-works/PacketAnatomy"
import { InteractiveGlobeClient } from "./how-it-works/InteractiveGlobeClient"

const RECAP = [
  {
    number: "01",
    title: "Deploy",
    description:
      "Hand-launched pico balloons reach ~30 km and begin drifting with stratospheric winds.",
  },
  {
    number: "02",
    title: "Sense",
    description:
      "Every wake cycle the payload fixes GPS, samples seven sensors, and tiers its power budget.",
  },
  {
    number: "03",
    title: "Uplink",
    description:
      "A 40-byte encrypted LoRaWAN frame reaches any community gateway within ~370 km.",
  },
  {
    number: "04",
    title: "Observe",
    description:
      "Data lands in Supabase and streams to Mission Control — realtime map, charts, open API.",
  },
]

export function HowItWorks() {
  const [isVisible, setIsVisible] = useState(false)
  const sectionRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setIsVisible(true)
      },
      { threshold: 0.05 },
    )
    if (sectionRef.current) observer.observe(sectionRef.current)
    return () => observer.disconnect()
  }, [])

  return (
    <section
      ref={sectionRef}
      id="how-it-works"
      className="border-b py-32 sm:py-40"
    >
      <div className="mx-auto max-w-5xl px-6 sm:px-8">
        <div
          className={`mx-auto max-w-2xl transition-all duration-1000 ${
            isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
          }`}
        >
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            How It Works
          </div>
          <h2 className="mt-6 text-4xl font-light tracking-tight text-foreground sm:text-5xl">
            A fleet of tiny platforms, drifting where nothing else loiters.
          </h2>
          <p className="mt-8 text-lg leading-relaxed text-muted-foreground">
            Stratolink is an end-to-end system: solar-powered pico-balloons
            in the lower stratosphere, a 40-byte LoRaWAN uplink that rides on
            community gateways, and a dashboard you can open in a browser. The
            next few sections peel the system apart, one layer at a time.
          </p>
        </div>
      </div>

      <div className="mx-auto mt-24 max-w-5xl px-6 sm:px-8">
        <AltitudeScale />
      </div>

      <div
        className={`mt-24 bg-[#05080f] py-20 sm:py-28 transition-opacity duration-1000 ${
          isVisible ? "opacity-100" : "opacity-0"
        }`}
      >
        <div className="mx-auto max-w-6xl px-6 sm:px-8">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-white/40">
              The Fleet
            </div>
            <h3 className="mt-5 text-3xl font-light tracking-tight text-white sm:text-4xl">
              A moving lattice of line-of-sight coverage.
            </h3>
            <p className="mt-5 text-base leading-relaxed text-white/60">
              Each balloon illuminates a ~370 km disc of Earth below it. As
              the fleet drifts, those discs wash over the planet. Drag the
              globe, change the fleet size, and watch coverage fill in.
            </p>
          </div>
          <InteractiveGlobeClient />
        </div>
      </div>

      <div className="mx-auto mt-24 max-w-5xl px-6 sm:px-8">
        <div className="mb-10 max-w-xl">
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            The Physics
          </div>
          <h3 className="mt-5 text-3xl font-light tracking-tight text-foreground sm:text-4xl">
            Why 15 kilometres reaches 440.
          </h3>
          <p className="mt-5 text-base leading-relaxed text-muted-foreground">
            The coverage radius isn't a radio thing — it's geometry. From the
            lower stratosphere you can see further because Earth curves away
            faster than the radio signal decays. Move the altitude slider.
          </p>
        </div>
        <SingleBalloonScene />
      </div>

      <div className="mx-auto mt-24 max-w-5xl px-6 sm:px-8">
        <DataFlowDiagram />
      </div>

      <div className="mx-auto mt-12 max-w-5xl px-6 sm:px-8">
        <PacketAnatomy />
      </div>

      <div className="mx-auto mt-28 max-w-5xl px-6 sm:px-8">
        <div className="grid gap-10 border-t border-border pt-12 sm:grid-cols-2 lg:grid-cols-4">
          {RECAP.map((step) => (
            <div key={step.number}>
              <div className="font-mono text-xs text-muted-foreground/70">
                {step.number}
              </div>
              <h4 className="mt-3 text-base font-normal text-foreground">
                {step.title}
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
