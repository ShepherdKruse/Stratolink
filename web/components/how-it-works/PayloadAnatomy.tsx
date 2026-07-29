"use client"

import { useState } from "react"

type Block = {
  id: string
  label: string
  part: string
  x: number
  y: number
  w: number
  h: number
  group: "compute" | "sense" | "power" | "rf"
  role: string
  current: string
}

const BLOCKS: Block[] = [
  {
    id: "mcu",
    label: "MCU + LoRa radio",
    part: "RAK3172 (STM32WLE5)",
    x: 30,
    y: 30,
    w: 160,
    h: 110,
    group: "compute",
    role: "Orchestrates each wake cycle; LoRaWAN MAC + sub-GHz PA integrated on die.",
    current: "1.69 µA · STOP2 sleep",
  },
  {
    id: "gps",
    label: "GNSS receiver",
    part: "u-blox MAX-M10S",
    x: 210,
    y: 30,
    w: 140,
    h: 90,
    group: "sense",
    role: "Position / altitude / ground speed. DYNMODEL 8 (airborne < 4g) set at boot to unlock fixes above 12 km.",
    current: "3 µA · V_BCKP",
  },
  {
    id: "baro",
    label: "Barometric pressure",
    part: "MS5611",
    x: 210,
    y: 140,
    w: 70,
    h: 50,
    group: "sense",
    role: "10–1,200 mbar; altitude cross-check and backup temperature source.",
    current: "0.6 µA · standby",
  },
  {
    id: "temp",
    label: "Precision temperature",
    part: "TMP117",
    x: 290,
    y: 140,
    w: 60,
    h: 50,
    group: "sense",
    role: "One-shot ±0.1 °C reading; primary air-temperature channel.",
    current: "0.25 µA · shutdown",
  },
  {
    id: "accel",
    label: "3-axis accel + INT1",
    part: "LIS2DH12",
    x: 30,
    y: 150,
    w: 85,
    h: 60,
    group: "sense",
    role: "Gravity-wave logging at 1 Hz; freefall interrupt wakes MCU into burst mode.",
    current: "2 µA · low-power",
  },
  {
    id: "uv",
    label: "UV + ambient light",
    part: "LTR-390UV-01",
    x: 125,
    y: 150,
    w: 75,
    h: 60,
    group: "sense",
    role: "Ozone saturation / cloud-cover proxy from UV and lux channels.",
    current: "1.5 µA · sleep",
  },
  {
    id: "mic",
    label: "Acoustic sensor",
    part: "TDK T3902 PDM",
    x: 30,
    y: 220,
    w: 120,
    h: 40,
    group: "sense",
    role: "Envelope-RMS energy for thunder / aircraft / envelope stress events.",
    current: "gated on-demand",
  },
  {
    id: "pmic",
    label: "Nano-power PMIC",
    part: "BQ25570",
    x: 210,
    y: 210,
    w: 140,
    h: 50,
    group: "power",
    role: "330 mV cold-start boost; tracks solar MPP; charges the supercap bank.",
    current: "488 nA · quiescent",
  },
  {
    id: "cap",
    label: "Energy store",
    part: "1 F · 5.5 V supercap",
    x: 30,
    y: 270,
    w: 180,
    h: 45,
    group: "power",
    role: "Bridges multi-hour darkness. 40 mΩ ESR keeps TX current surges in-band.",
    current: "≤5 µA leak",
  },
  {
    id: "solar",
    label: "Solar array",
    part: "2× 4.8 V / 50 mA cells",
    x: 220,
    y: 270,
    w: 130,
    h: 45,
    group: "power",
    role: "Harvest whenever the sun clears 5°; charge during the day, discharge at night.",
    current: "100 mA peak",
  },
  {
    id: "ant",
    label: "RF front end",
    part: "Wire monopole · 868/915/923",
    x: 360,
    y: 30,
    w: 20,
    h: 285,
    group: "rf",
    role: "Wire modeled across 868/915/923 MHz; exact-module and installed-match qualification remains region-specific.",
    current: "n/a",
  },
]

const GROUP_COLOR: Record<Block["group"], string> = {
  compute: "text-foreground",
  sense: "text-foreground/75",
  power: "text-foreground/75",
  rf: "text-foreground/75",
}

export function PayloadAnatomy() {
  const [hovered, setHovered] = useState<string | null>(null)
  const active = BLOCKS.find((b) => b.id === hovered) ?? null

  return (
    <div className="rounded-sm border border-border bg-card p-6 shadow-sm sm:p-10">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Payload Floorplan
          </div>
          <h3 className="mt-3 text-2xl font-light tracking-tight text-foreground sm:text-3xl">
            Everything that flies, on one PCB.
          </h3>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Hover a block to see what it does, which part ships it, and how
            much current it draws when idle.
          </p>
        </div>
        <div className="font-mono text-xs text-muted-foreground">
          total idle: &lt; 7 µA
        </div>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <svg
            viewBox="0 0 410 345"
            className="w-full text-foreground"
            onMouseLeave={() => setHovered(null)}
          >
            {/* PCB outline */}
            <rect
              x="12"
              y="12"
              width="386"
              height="321"
              rx="8"
              fill="currentColor"
              fillOpacity="0.025"
              stroke="currentColor"
              strokeOpacity="0.25"
              strokeWidth="1"
            />
            {/* Mounting holes */}
            {[
              [22, 22],
              [388, 22],
              [22, 323],
              [388, 323],
            ].map(([x, y]) => (
              <circle
                key={`${x}-${y}`}
                cx={x}
                cy={y}
                r="2.5"
                fill="none"
                stroke="currentColor"
                strokeOpacity="0.3"
              />
            ))}
            {/* Subtle grid */}
            {Array.from({ length: 12 }).map((_, i) => (
              <line
                key={`g-${i}`}
                x1={30 + i * 30}
                y1="14"
                x2={30 + i * 30}
                y2="331"
                stroke="currentColor"
                strokeOpacity="0.04"
              />
            ))}

            {/* Blocks */}
            {BLOCKS.map((b) => {
              const isActive = hovered === b.id
              return (
                <g
                  key={b.id}
                  onMouseEnter={() => setHovered(b.id)}
                  onFocus={() => setHovered(b.id)}
                  className="cursor-pointer outline-none"
                  tabIndex={0}
                  role="button"
                  aria-label={`${b.label} — ${b.part}`}
                >
                  <rect
                    x={b.x}
                    y={b.y}
                    width={b.w}
                    height={b.h}
                    rx="2"
                    fill="currentColor"
                    fillOpacity={isActive ? 0.18 : 0.045}
                    stroke="currentColor"
                    strokeOpacity={isActive ? 0.9 : 0.35}
                    strokeWidth={isActive ? 1.4 : 1}
                    className="transition-all"
                  />
                  <text
                    x={b.x + 8}
                    y={b.y + 16}
                    fontSize="10"
                    fill="currentColor"
                    className={`${GROUP_COLOR[b.group]} transition-opacity`}
                    fillOpacity={isActive ? 1 : 0.8}
                    fontFamily="sans-serif"
                  >
                    {b.label}
                  </text>
                  <text
                    x={b.x + 8}
                    y={b.y + 30}
                    fontSize="9"
                    fill="currentColor"
                    fillOpacity={isActive ? 0.7 : 0.45}
                    fontFamily="ui-monospace, SFMono-Regular, monospace"
                  >
                    {b.part}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        <div className="lg:sticky lg:top-24">
          {active ? (
            <div className="rounded-sm border border-border bg-muted/40 p-5">
              <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                {active.group === "compute"
                  ? "Compute + radio"
                  : active.group === "sense"
                    ? "Sensor"
                    : active.group === "power"
                      ? "Power"
                      : "RF"}
              </div>
              <div className="mt-3 text-lg font-light text-foreground">
                {active.label}
              </div>
              <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                {active.part}
              </div>
              <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                {active.role}
              </p>
              <div className="mt-4 border-t border-border pt-3 font-mono text-[11px] text-muted-foreground">
                {active.current}
              </div>
            </div>
          ) : (
            <div className="rounded-sm border border-dashed border-border/80 p-5 text-xs text-muted-foreground">
              Hover a block to inspect the component. Layout is schematic — a
              ~1:1 floorplan of the flight PCB.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
