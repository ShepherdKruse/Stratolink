import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import Link from "next/link"

export function Partners() {
  return (
    <section id="partners" className="border-b border-slate-200 bg-white py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Partners</h2>
          <p className="mt-4 text-lg leading-relaxed text-slate-600">
            Building an open community for atmospheric observation
          </p>
        </div>
        <div className="mt-12 grid gap-8 lg:grid-cols-2">
          <Card className="border-slate-200 bg-slate-50 p-8">
            <h3 className="text-lg font-semibold text-slate-900">We collaborate with</h3>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-slate-600">
              <li>• University atmospheric science departments</li>
              <li>• Government research laboratories</li>
              <li>• Nonprofit environmental organizations</li>
              <li>• Public weather and climate agencies</li>
              <li>• Community science networks</li>
            </ul>
          </Card>
          <Card className="border-slate-200 bg-slate-50 p-8">
            <h3 className="text-lg font-semibold text-slate-900">We're looking for</h3>
            <ul className="mt-4 space-y-2 text-sm leading-relaxed text-slate-600">
              <li>• Atmospheric science advisors</li>
              <li>• Field test sites and deployment partners</li>
              <li>• Data assimilation collaborators</li>
              <li>• Sensor calibration expertise</li>
              <li>• Open science advocates</li>
            </ul>
          </Card>
        </div>
        <div className="mt-8 text-center">
          <Button
            asChild
            variant="outline"
            size="lg"
            className="border-slate-300 text-slate-700 hover:bg-slate-50 bg-transparent"
          >
            <Link href="#contact">Inquire about partnership</Link>
          </Button>
        </div>
      </div>
    </section>
  )
}
