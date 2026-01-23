import { Card } from "@/components/ui/card"
import Link from "next/link"

export function DataSection() {
  const principles = [
    "Open: All datasets published under permissive licenses",
    "Documented: Complete metadata, units, and processing steps",
    "Auditable: Version-controlled with reproducible pipelines",
    "Reproducible: Code and calibration data publicly available",
  ]

  return (
    <section id="data" className="border-b border-slate-200 bg-slate-50 py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Data</h2>
          <p className="mt-4 text-lg leading-relaxed text-slate-600">
            Rigorous standards for open, validated environmental data
          </p>
        </div>
        <div className="mx-auto mt-12 max-w-3xl">
          <Card className="border-slate-200 bg-white p-8">
            <h3 className="text-lg font-semibold text-slate-900">Data Principles</h3>
            <ul className="mt-4 space-y-3">
              {principles.map((principle) => (
                <li key={principle} className="flex items-start text-sm leading-relaxed text-slate-600">
                  <span className="mr-3 mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-400" />
                  {principle}
                </li>
              ))}
            </ul>
            <div className="mt-8 space-y-4 border-t border-slate-200 pt-8">
              <h3 className="text-lg font-semibold text-slate-900">Resources</h3>
              <div className="space-y-2">
                <Link
                  href="#"
                  className="block text-sm text-slate-600 underline decoration-slate-300 underline-offset-2 transition-colors hover:text-slate-900"
                >
                  Sample dataset (coming soon)
                </Link>
                <Link
                  href="#"
                  className="block text-sm text-slate-600 underline decoration-slate-300 underline-offset-2 transition-colors hover:text-slate-900"
                >
                  Data schema documentation
                </Link>
                <Link
                  href="#"
                  className="block text-sm text-slate-600 underline decoration-slate-300 underline-offset-2 transition-colors hover:text-slate-900"
                >
                  GitHub repository
                </Link>
              </div>
            </div>
            <div className="mt-8 border-t border-slate-200 pt-8">
              <p className="text-sm leading-relaxed text-slate-600">
                We emphasize metadata discipline, calibration, validation, uncertainty quantification, and
                reproducibility in all published datasets.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </section>
  )
}
