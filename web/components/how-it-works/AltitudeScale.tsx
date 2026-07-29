"use client"

/**
 * A quiet altitude-axis diagram positioning Stratolink in the atmosphere
 * stack. Intentionally static — just a reference framing for the hero globe.
 */
export function AltitudeScale() {
  // Log-scale positions so the 35 km band is visible next to 20,000 km GPS
  const layers: Array<{
    label: string
    altitude: string
    pos: number
    emphasised?: boolean
    note?: string
  }> = [
    { label: "GNSS satellites", altitude: "20,200 km", pos: 0.05, note: "positioning, slow revisit" },
    { label: "Low Earth orbit", altitude: "400–1,200 km", pos: 0.18, note: "imaging, comms" },
    { label: "Mesosphere", altitude: "80 km", pos: 0.38 },
    { label: "Radiosondes (peak)", altitude: "30 km", pos: 0.58, note: "balloon bursts in ~2 h" },
    {
      label: "Stratolink",
      altitude: "10–20 km",
      pos: 0.7,
      emphasised: true,
      note: "persistent, low-cost, continuous",
    },
    { label: "Jet stream", altitude: "~10 km", pos: 0.82, note: "weather, airliners" },
    { label: "Surface", altitude: "0 km", pos: 0.94 },
  ]

  return (
    <div className="relative">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="max-w-xl">
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            The Observation Gap
          </div>
          <h3 className="mt-4 text-2xl font-light tracking-tight text-foreground sm:text-3xl">
            Above the weather, below the satellites.
          </h3>
          <p className="mt-5 text-base leading-relaxed text-muted-foreground">
            Radiosondes climb once and fall. Satellites see the planet but
            revisit slowly. Stratolink platforms loiter in the lower
            stratosphere for weeks, watching a moving patch of Earth
            continuously.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-4 border-t border-border pt-6">
            <Stat label="Altitude" value="10–20 km" />
            <Stat label="Cadence" value="60 s" />
            <Stat label="Coverage / balloon" value="~370–500 km" />
          </div>
        </div>

        <div className="relative">
          <svg
            viewBox="0 0 520 460"
            className="h-full w-full text-foreground"
          >
            {/* Vertical axis */}
            <line
              x1="110"
              y1="20"
              x2="110"
              y2="440"
              stroke="currentColor"
              strokeOpacity="0.2"
              strokeWidth="1"
            />

            {/* Tick marks + labels */}
            {layers.map((layer) => {
              const y = 20 + layer.pos * 420
              return (
                <g key={layer.label}>
                  <line
                    x1="104"
                    y1={y}
                    x2={layer.emphasised ? 520 : 180}
                    y2={y}
                    stroke="currentColor"
                    strokeOpacity={layer.emphasised ? 0.35 : 0.12}
                    strokeWidth="1"
                    strokeDasharray={layer.emphasised ? undefined : "2 3"}
                  />
                  <text
                    x="98"
                    y={y + 3}
                    fontSize="10"
                    textAnchor="end"
                    fill="currentColor"
                    fillOpacity="0.55"
                    fontFamily="sans-serif"
                  >
                    {layer.altitude}
                  </text>

                  <g transform={`translate(${layer.emphasised ? 190 : 190}, ${y})`}>
                    <text
                      x="0"
                      y="-2"
                      fontSize={layer.emphasised ? "14" : "12"}
                      fill="currentColor"
                      fillOpacity={layer.emphasised ? 1 : 0.8}
                      fontFamily="sans-serif"
                      fontWeight={layer.emphasised ? 500 : 300}
                    >
                      {layer.label}
                    </text>
                    {layer.note && (
                      <text
                        x="0"
                        y="14"
                        fontSize="10"
                        fill="currentColor"
                        fillOpacity="0.5"
                        fontFamily="sans-serif"
                      >
                        {layer.note}
                      </text>
                    )}
                  </g>

                  {layer.emphasised && (
                    <circle cx="110" cy={y} r="4" fill="currentColor" />
                  )}
                </g>
              )
            })}

            {/* Band highlighting the Stratolink zone */}
            <rect
              x="111"
              y={20 + 0.66 * 420}
              width="409"
              height={0.1 * 420}
              fill="currentColor"
              fillOpacity="0.05"
            />
          </svg>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-base font-light text-foreground">{value}</div>
    </div>
  )
}
