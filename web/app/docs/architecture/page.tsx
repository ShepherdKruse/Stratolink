import Link from "next/link"
import { Navigation } from "@/components/navigation"
import { Footer } from "@/components/footer"
import { AltitudeScale } from "@/components/how-it-works/AltitudeScale"
import { SingleBalloonScene } from "@/components/how-it-works/SingleBalloonScene"
import { DataFlowDiagram } from "@/components/how-it-works/DataFlowDiagram"
import { PacketAnatomy } from "@/components/how-it-works/PacketAnatomy"
import { PayloadAnatomy } from "@/components/how-it-works/PayloadAnatomy"
import { InteractiveGlobeClient } from "@/components/how-it-works/InteractiveGlobeClient"

export default function ArchitecturePage() {
  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main>
        <div className="border-b bg-background">
          <div className="mx-auto max-w-4xl px-6 py-16 sm:px-8 sm:py-24">
            <Link
              href="/docs"
              className="mb-8 inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <svg
                className="mr-2 w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              Back to Documentation
            </Link>
            <h1 className="text-4xl font-light tracking-tight text-foreground sm:text-5xl">
              System Architecture
            </h1>
            <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
              A tour of the full stack — payload, link layer, cloud, client —
              told through interactive diagrams. The same components that
              power the{" "}
              <Link
                href="/#how-it-works"
                className="underline underline-offset-4"
              >
                homepage
              </Link>
              , annotated with more depth.
            </p>
          </div>
        </div>

        <div className="mx-auto max-w-5xl px-6 py-20 sm:px-8 sm:py-24">
          <section>
            <Heading
              kicker="01 · Context"
              title="Where Stratolink sits"
              body="Between the jet stream and low-Earth orbit, there's a sparsely-observed band. Stratolink fills it with durable, cheap platforms that stay up for weeks."
            />
            <div className="mt-10">
              <AltitudeScale />
            </div>
          </section>

          <section className="mt-28">
            <Heading
              kicker="02 · The fleet"
              title="Coverage as geometry"
              body="Every balloon illuminates a disc of Earth defined by line-of-sight to the horizon. The fleet drifts with the wind, and coverage sweeps the planet continuously."
            />
          </section>
        </div>

        <div className="bg-[#05080f] py-20 sm:py-24">
          <div className="mx-auto max-w-6xl px-6 sm:px-8">
            <InteractiveGlobeClient />
          </div>
        </div>

        <div className="mx-auto max-w-5xl px-6 py-20 sm:px-8 sm:py-24">
          <section>
            <Heading
              kicker="03 · Line-of-sight physics"
              title="From altitude to horizon"
              body="The horizon distance is d = √(2Rh + h²), where R is Earth's radius and h is balloon altitude. At 15 km, d ≈ 437 km — so a single balloon sees roughly 600,000 km² of Earth below it."
            />
            <div className="mt-10">
              <SingleBalloonScene />
            </div>
          </section>

          <section className="mt-28">
            <Heading
              kicker="04 · The hardware"
              title="Seven sensors and a radio, on one board"
              body="Every part on the flight PCB has a reason and a power budget. The same floorplan we use to trace data integrity during flight."
            />
            <div className="mt-10">
              <PayloadAnatomy />
            </div>
          </section>

          <section className="mt-28">
            <Heading
              kicker="05 · The link"
              title="Sleep, sample, uplink, repeat"
              body="Every wake cycle follows the same sequence. Between flight cycles the MCU uses watchdog-safe STOP1 sleep."
            />
            <div className="mt-10">
              <DataFlowDiagram />
            </div>
          </section>

          <section className="mt-28">
            <Heading
              kicker="06 · The payload"
              title="What's in the 40 bytes"
              body="Big-endian, AES-128-CMAC encrypted, decoded by /api/ttn-webhook on arrival. Hover a field to see the encoding."
            />
            <div className="mt-10">
              <PacketAnatomy />
            </div>
          </section>

          <section className="mt-28 rounded-sm border border-border bg-card p-8 sm:p-10">
            <h2 className="text-2xl font-light tracking-tight text-foreground">
              Keep reading
            </h2>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <NextLink
                href="/docs/hardware"
                title="Hardware setup"
                body="Flash the firmware, configure your LoRaWAN region, wire the antenna."
              />
              <NextLink
                href="/docs/api"
                title="API reference"
                body="Query live and historical telemetry from Supabase."
              />
              <NextLink
                href="/docs/dashboard"
                title="Mission Control"
                body="Watch a live map, inspect charts, export CSV."
              />
              <NextLink
                href="/docs/troubleshooting"
                title="Troubleshooting"
                body="What to check when a device is silent, lost, or misreporting."
              />
            </div>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  )
}

function Heading({
  kicker,
  title,
  body,
}: {
  kicker: string
  title: string
  body: string
}) {
  return (
    <div className="max-w-2xl">
      <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
        {kicker}
      </div>
      <h2 className="mt-4 text-3xl font-light tracking-tight text-foreground sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-relaxed text-muted-foreground">
        {body}
      </p>
    </div>
  )
}

function NextLink({
  href,
  title,
  body,
}: {
  href: string
  title: string
  body: string
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-sm border border-border bg-background p-5 transition-all hover:border-foreground/30"
    >
      <div className="text-sm font-normal text-foreground">{title}</div>
      <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
        {body}
      </div>
      <div className="mt-4 flex items-center text-[11px] font-medium text-foreground/60 group-hover:text-foreground">
        Continue
        <svg
          className="ml-2 h-3 w-3 transition-transform group-hover:translate-x-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
      </div>
    </Link>
  )
}
