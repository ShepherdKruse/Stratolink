# v1.1 peer review, 14 October 2026

Review of the board published at `e6f5200208cf433aa2baf0dcad80d9d9ef26cd25`. Baseline PCB SHA-256: `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`.

The RF feedback identifies a real layout problem. The capacitor, pull-up and programming suggestions need qualifications before changing hardware.

| Feedback | Finding | Disposition |
|---|---|---|
| Antenna feed crosses a switching node | The front GNSS feed crosses the rear `Net-(U1-LBOOST)` trace at approximately (62.882, 40.769) mm. There is no intervening ground layer. The LoRa feed is in a different area. | The short detour was rejected after return-path review. An upper-board placement revision is required. |
| Improve RF grounding | Both layers have ground fill, but fill is not a continuous reference plane. C5's positive rear land also lies under U3's RF-input pad. | A reroute can remove the switch crossing. Full RF-ground cleanup needs a placement change or a qualified transition. |
| Use two sets of 10 kΩ pull-ups | Two 10 kΩ resistors in parallel on each line give 5 kΩ, slightly weaker than the existing 4.7 kΩ. GPS internal pull-ups also contribute. | Keep the existing values pending a measured rise-time check. Four devices alone do not establish excessive capacitance. |
| Programming pinout is wrong | The standard 32-pin RAK3172 module uses SWDIO pin 7, SWCLK pin 8, BOOT0 pin 21 and reset pin 22. These match the board and flown revision. The RAK3172-F has a different pinout. | Preserve the verified mapping. Confirm the actual cable adapter. |
| C8 and the other 10 µF capacitor are useless | C8 and C21 are 3.3 V bulk decouplers. RAK's reference circuit includes 10 µF plus 100 nF. Their selected ceramic parts lose substantial capacitance under DC bias. | Retain both. Evaluate effective capacitance and rail transients before reducing values or packages. |
| UART is being used as a bus and should be length matched | GNSS UART is a crossed point-to-point link with header taps. It is asynchronous and single-ended, with no TX/RX matching requirement. The header introduces a possible external-driver conflict. | Document adapter connections and isolation. Review edge speed and attached wires rather than adding matching meanders. |

## RF scope

The exposed antenna wires radiate; surrounding those wires with ground would change their operation. The PCB feed needs an appropriate impedance, nearby return conductor and separation from noise. On this two-layer board, the useful arrangement is coplanar ground beside the feed, a continuous opposite-side reference where possible and short ground stitching connections.

u-blox MAX-M10S integration manual UBX-20053088 R05, pages 80–81, recommends a short 50 Ω RF connection, grounded coplanar routing, solid ground beneath RF parts and ground vias. A clean DRC result cannot establish impedance, radiation efficiency, receiver noise or immunity to the converter.

The current GNSS input sits above a supercapacitor supply land. Preserve this as an explicit limitation of any route-only improvement. Do not describe such a change as complete shielding or a fully controlled 50 Ω feed. A larger placement revision should address the input transition, converter separation and GNSS bypass location together.

The screened west detour would lengthen the main feed from 13.439 mm to 19.069 mm, about 42%. It also passes over balancing-circuit supply/output/reference copper and still has the RF-input/supercapacitor overlap. It is rejected and has not been applied to the board.

## Digital and bench connections

J20 is SWD. The TC2030-CTX footprint mapping is 1 Vref, 2 SWDIO, 3 reset, 4 SWCLK, 5 GND, 6 SWO. Other cable adapters require their own mapping check. The RAK vendor UART-update pins are module pins 1/2, not the GNSS UART1 pins 4/5.

J4.5 shares the MCU receive net with the GPS transmitter through 33 Ω. Connecting another push-pull transmitter there can cause contention. A passive receive-only monitor is different from an adapter that drives the line. R9 currently ties BOOT0 to ground through 0 Ω; do not drive that net high with R9 fitted. Normal SWD programming does not require doing so.

The installed firmware starts I²C at 100 kHz, but MAX-M10S and AS7331 impose 300 ns rise-time limits. Do not apply a relaxed 1 µs limit just because the bus runs slowly. Total capacitance includes IC pins, traces, pads and any attached measurement leads. Check both lines at the farthest devices with a low-capacitance probe.

## Power follow-up

Keep C8/C21 and the regulator's local bypass capacitors. The TI output-capacitance table has a 10 µF minimum and 22 µF nominal value, while its application guidance recommends 22 µF for most applications. Nominal values and typical bias curves do not establish a worst-case effective value over voltage, tolerance and temperature.

The power review also identified a distant GNSS bypass capacitor, C10, and a ferrite bead whose specified maximum DC resistance exceeds u-blox's 0.2 Ω series-resistance guidance. These warrant a focused supply-layout and component review. They do not establish the cause of past flight GPS faults.

## Fabrication and routing style

The copper cleanup is promoted to `hardware/pcb`. PCB SHA-256: `4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54`. The schematic is unchanged. The strict published project is `915d9f9c4bc8c1eb0866031bf765ff08dc41a7b5bea4fb158ca26c1032ef93cd`; it now enforces 0.10 mm minimum connection/groove widths with error severity.

- Widen the U8 pad/via landing and close the narrow ground connection.
- Close the tiny U1, output-rail and ground pockets; widen the U6 ground bridge from 0.15 to 0.20 mm.
- Round the identified electrical junctions with small same-net copper fillets, retaining the original track centerlines and arcs.
- Remove three microscopic logo specks and fill only its tiny internal hole.
- Round the two copper labels using their native rendered outlines. Editable originals remain on F.Fab, grouped with the copper; no silkscreen is added.

All 68 footprints, 259 physical pads, 250 logical pad connections, vias and the board outline are preserved. Six short conductors are added and one existing width changes. Native strict DRC, open-connection and schematic-parity checks are zero; ERC has zero unexcluded findings. The independent full-copper screen reports zero candidates under its explicit thresholds on both faces. [Scope and proof](fabrication/final-independent.json), [independent geometry review](fabrication/copper-final4-independent-review.json), [before/after views](fabrication/candidate/before-after.pdf), [change ledgers and reproduction](fabrication/candidate/README.md).

The screen includes the actual filled copper and artwork, rather than only trace centerlines. It does not certify every etching process or replace supplier CAM review. JLC's [layout guidance](https://jlcpcb.com/features/layout) explicitly lists acute-angle etching traps, small annular rings and mask slivers as fabrication concerns. Small fillets also touch the inherited RF bends; this cleanup does not resolve the RF placement issue described above.

## Evidence and reproducibility

- [Baseline hashes](baseline/manifest.json)
- [Layer plot of the RF crossing](rf/rf-top-copper.png)
- [Native RF geometry](rf/native-rf-geometry.json)
- [I²C, programming and UART review](digital/README.md)
- [Capacitor and power review](power/README.md)
- [Current RAK manufacturer text](sources/rak3172-datasheet.txt)
- [Tag-Connect source and mapping](sources/tag-connect-pinout.md)
- [Independent layout comparison](verify_layout.py)

The canonical project file contained pre-existing edits disabling the mask-bridge check, setting mask-to-foreign-copper clearance to zero and restoring an obsolete LTR390 ERC exclusion. Those edits are recorded in `baseline/user-project.diff` and are preserved. Any candidate checks use the stricter published project settings; do not confuse those settings with the current editor's overrides.

The saved JLC Y24 cart refers to the earlier hashed package. A CAD revision is not automatically reflected in that cart. Manufacturing exports, supplier review and physical RF/power qualification must match the chosen final revision.
