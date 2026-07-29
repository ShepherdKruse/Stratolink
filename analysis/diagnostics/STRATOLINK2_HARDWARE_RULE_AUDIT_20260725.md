# StratoLink-2 hardware rule and netlist audit

Prepared 2026-07-25 from the current local schematic and PCB files. This is a
design-file audit; it does not substitute for inspection, continuity, RF match,
or environmental testing of the manufactured StratoLink-2 payload.

## Result

The current schematic netlist agrees with every flight-firmware MCU pin used by
the final candidate:

| Function | Firmware | Current netlist |
|---|---|---|
| GNSS UART | PB7 RX / PB6 TX | U2 pin 5 RX / pin 4 TX through the GNSS nets |
| GNSS reset | PA0, active low | U2 pin 29 to U3 pin 9 `RESET_N` |
| Shared I2C | PA11 SDA / PA12 SCL | U2 pin 10 SDA / pin 9 SCL to U3-U7 |
| Accelerometer interrupt | PA8 | U2 pin 19 to U7 pin 12 `INT1` |
| Microphone | PB3 clock / PB4 data | U2 pin 32 `CLK` / pin 31 `PDM` |
| Power telemetry | PA10 VSTOR / PA15 solar / PB5 VBAT_OK | U2 pins 25 / 3 / 30 |
| SWD | PA13 SWDIO / PA14 SWCLK / reset | U2 pins 7 / 8 / 22 to J20 |

The sensor-address straps also agree with the firmware:

| Device | Strap evidence | Firmware address |
|---|---|---|
| LIS2DH12 U7 | SDO/SA0 to GND | `0x18` |
| TMP117 U5 | ADD0 to GND | `0x48` |
| LTR390 U6 | Fixed | `0x53` |
| MS5611 U4 | PS and CSB to 3.3 V | I2C, `0x76` |
| MAX-M10S U3 | Fixed DDC address | `0x42` |

For the MS5611, TE's datasheet defines the seven-bit address as `111011C`,
where `C` is the complement of CSB. Therefore the board's CSB-high strap
selects `0x76`; the prior firmware comment saying CSB was low was incorrect,
but the compiled address was and remains correct. The plausible, continuous
pressure stream and prior physical PROM CRC provide independent device-path
evidence.

## Fresh ERC

KiCad CLI 10.0.0 completed a fresh JSON ERC against
`hardware/pcb/stratolink.kicad_sch` with 20 errors and 50 warnings:

- 16 `pin_not_connected` reports cover deliberately unused MCU, GNSS, sensor,
  and SWO pins that lack proper no-connect declarations.
- Three `power_pin_not_driven` reports cover externally driven solar and
  Tag-Connect power/ground nets that lack ERC power-source flags.
- The unused J20 SWO input is additionally reported as `pin_not_driven`.
- One GND power symbol remains unannotated as `#PWR?`, which causes the netlist
  export's annotation warning.
- Most warnings arise from electrical pin types in imported/custom symbols.

These findings do not demonstrate a fault on the manufactured board, but the
schematic does not currently pass a clean ERC. A future design-file cleanup
should annotate the remaining power symbol, add explicit no-connect markers,
add truthful power flags to externally driven nets, and correct imported symbol
electrical types without changing connectivity.

## PCB DRC status

A fresh PCB DRC could not be obtained. KiCad CLI 10.0.0 was retried during the
active shaded soak in both its native architecture and its x86_64 slice under
Rosetta; both aborted before writing a temporary report (the native run emits
Swift's `Array index out of range`, while the x86_64 run exits 134 without a
report). The bundled Python API also aborts inside KiCad's report path. This is
a tool failure, not a passing DRC.

The failure was reproduced again on 2026-07-27 against the current 987,731-byte
board, SHA-256
`2924cfa59d48c1446488d715834e84ea634516e622ed59915fb72521e9595190`.
Both a JSON `--severity-all --exit-code-violations` invocation and an ordinary
error/warning report invocation exited 133 with Swift `Array index out of
range` and created no report. The exact KiCad CLI 10.0.0 executable was
2,131,968 bytes, SHA-256
`998aed348399000335b0e29edf747daa18819f2ac417bac066f4216fdc5d90d1`.
Neither invocation used `--refill-zones` or `--save-board`; the board hash was
unchanged. This fresh reproduction narrows the tool/board pair but still does
not classify or waive any layout violation.

The checked-in `hardware/pcb/drc-final.json` is stale: it was generated
2026-02-26 with KiCad 8.0.3 and reports 84 violations (17 errors, 67 warnings)
plus one unconnected item. Its errors include one keepout violation, one
courtyard overlap, six starved thermals, and nine solder-mask bridges. A
UUID-level comparison against the current board makes the residual scope more
precise: 16 of those 17 error findings still reference the same present board
objects. These are all nine mask-aperture findings (eight around the 0.5 mm
pitch LIS2DH12 plus one mask graphic/ground-track finding), all six one-spoke
thermal findings, and the D1/AE1 courtyard overlap. The old keepout-violation
track UUID and the old unconnected-via UUID are absent; three of four dangling
track UUIDs and all three dangling-via UUIDs are also absent. Object survival
does not prove that KiCad 10 would reproduce a violation, but it prevents the
old errors from being dismissed merely as references to deleted geometry.
The operating assembled board makes a gross copper short unlikely; it does not
turn mask-dam, solderability, assembly-clearance, or thermal-spoke findings into
a clean manufacturing release.

## T3902 acoustic-port geometry

`microphone_port_audit.py` binds the production `MK1` BOM row and the actual
embedded `lib:MIC_T3902` footprint in the current PCB to TDK InvenSense's T3902
datasheet. The 0.500 mm NPTH bore is inside TDK's recommended 0.500-1.000 mm PCB
hole range and is larger than the package's 0.375 mm sound port, but it is
exactly at the lower allowed boundary. The four 0.725 x 0.522 mm signal pads
and the custom 1.626/1.024 mm OD/ID ground ring agree with TDK's nominal
0.725 x 0.522 mm and 1.625/1.025 mm land-pattern dimensions within 2 um. Eight
explicit paste polygons also match TDK's suggested 0.625 x 0.422 mm signal
apertures and nominal 1.625/1.125 mm ground-ring OD/ID within 2 um. They leave
0.312 mm radial clearance beyond the drilled hole edge, so the design does not
intentionally print paste over the bore.

That positive geometry screen is not a physical microphone pass. The 1.725 mm
mask opening still participates in the surviving historical mask-bridge error
with a connected GND track. Because the acoustic bore has no lower-bound
margin, solder, flux, coating, tape, debris, cover misalignment, or fabrication
tolerance could obstruct a manufactured board even when digital PDM capture is
active. Before launch, inspect/backlight the exact port and preserve a photo;
then run quiet and controlled sweep/multitone/click stimuli on the frozen image
using its new attempt/capture/failure/event/variance/floor diagnostics. Repeat
with flight cover geometry and active harvesting after the supercap is fitted.
The shaded precursor's isolated fCnt 74 event remains unclassified because its
one-bit event flag cannot distinguish real sound from handling or electrical
self-noise. The transitional v2 wire contract now separately reports capture
availability; it prevents capture failure/skip from masquerading as quiet but
does not classify the source of a valid anomaly.

## Launch implication

The pin/address audit is positive and agrees with live payload behavior.
However, hardware design-rule sign-off remains `PARTIAL`: the present board can
continue HIL and soak testing, while a clean current PCB DRC and final physical
inspection remain required evidence before declaring the design release clean.
