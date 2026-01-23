import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import Link from "next/link"

export function PilotProgram() {
  return (
    <section id="pilot" className="border-b border-slate-200 bg-white py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Pilot Program</h2>
          <p className="mt-4 text-lg leading-relaxed text-slate-600">
            Partner with us to validate the StratoLink system in real-world conditions
          </p>
        </div>
        <Card className="mx-auto mt-12 max-w-3xl border-slate-200 bg-slate-50 p-8">
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Objective</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                Test and validate sensor accuracy, data transmission reliability, and dataset quality in operational
                environments.
              </p>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Scope</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                20–50 sensor nodes deployed over 1–3 weeks in a defined geographic region.
              </p>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-900">What we provide</h3>
              <ul className="mt-2 space-y-1 text-sm leading-relaxed text-slate-600">
                <li>• Sensor hardware and deployment support</li>
                <li>• Data collection and processing infrastructure</li>
                <li>• Technical documentation and training</li>
                <li>• Calibrated datasets with metadata</li>
              </ul>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-slate-900">What we request from partners</h3>
              <ul className="mt-2 space-y-1 text-sm leading-relaxed text-slate-600">
                <li>• Scientific advisory and feedback on data quality</li>
                <li>• Access to comparison benchmarks (radiosonde, reanalysis data)</li>
                <li>• Field site coordination and regulatory support</li>
              </ul>
            </div>
          </div>
          <div className="mt-8 text-center">
            <Button asChild size="lg" className="bg-slate-700 text-white hover:bg-slate-800">
              <Link href="#contact">Start a pilot conversation</Link>
            </Button>
          </div>
        </Card>
      </div>
    </section>
  )
}
