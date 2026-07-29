"use client"

import { useState } from "react"

type Field = {
  name: string
  byteStart: number
  byteEnd: number // inclusive
  units: string
  sample: string
  note?: string
}

// Mirrors firmware/DOCUMENTATION.md §5 — 40-byte big-endian telemetry v2.
const FIELDS: Field[] = [
  {
    name: "Latitude",
    byteStart: 0,
    byteEnd: 3,
    units: "deg × 1e7",
    sample: "37.4712340",
    note: "int32, signed",
  },
  {
    name: "Longitude",
    byteStart: 4,
    byteEnd: 7,
    units: "deg × 1e7",
    sample: "−122.2567890",
    note: "int32, signed",
  },
  {
    name: "Altitude",
    byteStart: 8,
    byteEnd: 11,
    units: "meters",
    sample: "32,104",
    note: "int32, MSL",
  },
  {
    name: "Temperature",
    byteStart: 12,
    byteEnd: 13,
    units: "°C × 0.1",
    sample: "−56.4",
    note: "int16, TMP117 or baro fallback",
  },
  {
    name: "Pressure",
    byteStart: 14,
    byteEnd: 15,
    units: "hPa × 0.1",
    sample: "9.5",
    note: "uint16, MS5611",
  },
  {
    name: "Solar",
    byteStart: 16,
    byteEnd: 17,
    units: "mV",
    sample: "4,812",
    note: "uint16, cell bank",
  },
  {
    name: "VSTOR",
    byteStart: 18,
    byteEnd: 19,
    units: "mV",
    sample: "4,520",
    note: "uint16, supercap",
  },
  {
    name: "Ground speed",
    byteStart: 20,
    byteEnd: 21,
    units: "m/s × 0.01",
    sample: "28.14",
    note: "uint16",
  },
  {
    name: "Heading",
    byteStart: 22,
    byteEnd: 23,
    units: "° × 0.01",
    sample: "264.37",
    note: "uint16",
  },
  {
    name: "GPS sats",
    byteStart: 24,
    byteEnd: 24,
    units: "count",
    sample: "9",
    note: "uint8",
  },
  {
    name: "Accel X",
    byteStart: 25,
    byteEnd: 26,
    units: "m/s² × 0.01",
    sample: "−0.12",
    note: "int16, LIS2DH12",
  },
  {
    name: "Accel Y",
    byteStart: 27,
    byteEnd: 28,
    units: "m/s² × 0.01",
    sample: "0.04",
    note: "int16",
  },
  {
    name: "Accel Z",
    byteStart: 29,
    byteEnd: 30,
    units: "m/s² × 0.01",
    sample: "−9.81",
    note: "int16",
  },
  {
    name: "UV index",
    byteStart: 31,
    byteEnd: 31,
    units: "0–15+",
    sample: "12",
    note: "uint8, LTR-390",
  },
  {
    name: "Ambient lux",
    byteStart: 32,
    byteEnd: 33,
    units: "lux",
    sample: "118,400",
    note: "uint16",
  },
  {
    name: "Status",
    byteStart: 34,
    byteEnd: 34,
    units: "bit field",
    sample: "quiet · FULL · software reset",
    note: "acoustic/power code (including unavailable), reset cause, command-valid",
  },
  {
    name: "Boot count",
    byteStart: 35,
    byteEnd: 35,
    units: "mod 256",
    sample: "17",
    note: "retained reset counter, low byte",
  },
  {
    name: "GPS fix age",
    byteStart: 36,
    byteEnd: 37,
    units: "minutes",
    sample: "20",
    note: "0xFFFF means no fresh fix this boot",
  },
  {
    name: "Command ACK",
    byteStart: 38,
    byteEnd: 38,
    units: "sequence",
    sample: "166",
    note: "last durably applied command",
  },
  {
    name: "Radio activity",
    byteStart: 39,
    byteEnd: 39,
    units: "bit field",
    sample: "relay on · 2 forwards · 1 tag",
    note: "relay state plus saturated relay/CTT deltas",
  },
]

const BYTE_COUNT = 40

export function PacketAnatomy() {
  const [hovered, setHovered] = useState<number | null>(null)

  const hoveredField =
    hovered === null ? null : FIELDS.find((_, i) => i === hovered) ?? null
  const isByteActive = (byteIdx: number) => {
    if (hoveredField === null) return false
    return (
      byteIdx >= hoveredField.byteStart && byteIdx <= hoveredField.byteEnd
    )
  }

  return (
    <div className="rounded-sm border border-border bg-card p-6 shadow-sm sm:p-10">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Uplink Frame
          </div>
          <h3 className="mt-3 text-2xl font-light tracking-tight text-foreground sm:text-3xl">
            40 bytes of flight truth.
          </h3>
        </div>
        <div className="font-mono text-xs text-muted-foreground">
          big-endian · AES-128-CMAC
        </div>
      </div>

      <div className="mt-10 grid grid-cols-[repeat(40,minmax(0,1fr))] gap-[3px]">
        {Array.from({ length: BYTE_COUNT }).map((_, i) => {
          const active = isByteActive(i)
          return (
            <div
              key={i}
              className={`aspect-square rounded-[2px] border transition-all ${
                active
                  ? "border-foreground bg-foreground"
                  : "border-border bg-background"
              }`}
            />
          )
        })}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>byte 0</span>
        <span>byte 39</span>
      </div>

      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {FIELDS.map((field, idx) => {
          const active = hovered === idx
          return (
            <button
              key={field.name}
              type="button"
              onMouseEnter={() => setHovered(idx)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(idx)}
              onBlur={() => setHovered(null)}
              className={`group flex flex-col gap-2 rounded-sm border px-4 py-3 text-left transition-all ${
                active
                  ? "border-foreground/50 bg-muted/60"
                  : "border-border bg-background hover:border-foreground/30"
              }`}
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-mono text-[10px] text-muted-foreground">
                  {field.byteStart === field.byteEnd
                    ? `byte ${field.byteStart}`
                    : `bytes ${field.byteStart}–${field.byteEnd}`}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground/80">
                  {field.units}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-normal text-foreground">
                  {field.name}
                </span>
                <span className="font-mono text-xs text-foreground/80">
                  {field.sample}
                </span>
              </div>
              {field.note && (
                <div className="text-[11px] text-muted-foreground/80">
                  {field.note}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
