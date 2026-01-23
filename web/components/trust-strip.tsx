export function TrustStrip() {
  const partners = ["University Partner", "Research Lab", "Public Agency", "Community Science"]

  return (
    <section className="border-b border-slate-200 bg-slate-100 py-8">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <p className="text-sm font-medium text-slate-600">Built for researchers, educators, and public agencies</p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-8">
            {partners.map((partner) => (
              <div
                key={partner}
                className="flex h-12 items-center justify-center px-6 text-sm font-medium text-slate-400 grayscale"
              >
                {partner}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
