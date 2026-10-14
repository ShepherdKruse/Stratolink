# v1.1 peer review, 14 October 2026

Review of the board published at `e6f5200208cf433aa2baf0dcad80d9d9ef26cd25`. Baseline PCB SHA-256: `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`.

The RF feedback identified a real layout problem. The corrected layout is now in `hardware/pcb`, PCB SHA-256 `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`. Native and independent checks pass. The capacitor, pull-up and programming suggestions were checked against the exact parts and retained as described below.

| Feedback | Finding | Disposition |
|---|---|---|
| Antenna feed crosses a switching node | The front GNSS feed crosses the rear `Net-(U1-LBOOST)` trace at approximately (62.882, 40.769) mm. There is no intervening ground layer. The LoRa feed is in a different area. | Moved AE2/D3 and shifted C5 right. The new 6.575 mm feed removes this crossing; the longer detour was rejected. |
| Improve RF grounding | Both layers have ground fill, but fill is not a continuous reference plane. C5's positive rear land also lies under U3's RF-input pad. | The C5 shift removes that overlap. Connected ground lies beside the feed and beneath it beyond the antenna-pad transition. |
| Use two sets of 10 kΩ pull-ups | Two 10 kΩ resistors in parallel on each line give 5 kΩ, slightly weaker than the existing 4.7 kΩ. GPS internal pull-ups also contribute. | Keep the existing values pending a measured rise-time check. Four devices alone do not establish excessive capacitance. |
| Programming pinout is wrong | The standard 32-pin RAK3172 module uses SWDIO pin 7, SWCLK pin 8, BOOT0 pin 21 and reset pin 22. These match the board and flown revision. The RAK3172-F has a different pinout. | Preserve the verified mapping. Confirm the actual cable adapter. |
| C8 and the other 10 µF capacitor are useless | C8 and C21 are 3.3 V bulk decouplers. RAK's reference circuit includes 10 µF plus 100 nF. Their selected ceramic parts lose substantial capacitance under DC bias. | Retain both. Evaluate effective capacitance and rail transients before reducing values or packages. |
| UART is being used as a bus and should be length matched | GNSS UART is a crossed point-to-point link with header taps. It is asynchronous and single-ended, with no TX/RX matching requirement. The header introduces a possible external-driver conflict. | Document adapter connections and isolation. Review edge speed and attached wires rather than adding matching meanders. |

## RF scope

The exposed antenna wires radiate; surrounding those wires with ground would change their operation. The PCB feed needs an appropriate impedance, nearby return conductor and separation from noise. On this two-layer board, the useful arrangement is coplanar ground beside the feed, a continuous opposite-side reference where possible and short ground stitching connections.

u-blox MAX-M10S integration manual UBX-20053088 R05, pages 80–81, recommends a short 50 Ω RF connection, grounded coplanar routing, solid ground beneath RF parts and ground vias. A clean DRC result cannot establish impedance, radiation efficiency, receiver noise or immunity to the converter.

The accepted revision moves AE2 to (55.3, 47.85) mm, with its nominal 48 mm wire exiting left, and D3 to (58.0, 45.05) mm. C5 shifts 1.8 mm right while retaining its flat rear fit, polarity and balancing circuit. Only these three component poses change in this pass. The receiver and switching loops stay fixed. Local `/VBAT`, `/SC_MID`, +3.3 V, SCL and GND routes are reconciled; all 259 physical pads and 250 logical connections are checked independently.

The 0.45 mm feed is 6.575 mm long, about 51% shorter than the original. Both faces have local GND; a 0.30 mm front guard and nearby stitching connect to the receiver ground network. U3.10/U3.12 and D3.1 use solid GND connections. All 144 non-pad transverse samples have ground on both sides. The opposite-layer reference is continuous beyond the antenna-hole clearance transition within the stated 5 µm geometric tolerance; no foreign rear copper overlaps the screened feed or receiver launch.

The finite side grounds and pad/ESD transitions are not an ideal uniform transmission line. The nominal grounded-coplanar model gives 48.5 Ω with stated assumptions, not a supplier impedance guarantee or measured RF performance. See [placement and limits](rf/left-feed-review.md), [model](rf/impedance.md), [independent ground reference](digital/final-rf-reference.json) and [mechanical margins](power/RF-MECHANICAL-REVIEW.md). The distant GNSS bypass and bead resistance remain separate follow-ups.

The earlier 19.069 mm west detour was rejected because it crossed additional rear supply/balancer copper and retained the capacitor overlap. It was never promoted. Historical exploratory reports are preserved against their own hashes.

## Digital and bench connections

J20 is SWD. The TC2030-CTX footprint mapping is 1 Vref, 2 SWDIO, 3 reset, 4 SWCLK, 5 GND, 6 SWO. Other cable adapters require their own mapping check. The RAK vendor UART-update pins are module pins 1/2, not the GNSS UART1 pins 4/5.

J4.5 shares the MCU receive net with the GPS transmitter through 33 Ω. Connecting another push-pull transmitter there can cause contention. A passive receive-only monitor is different from an adapter that drives the line. R9 currently ties BOOT0 to ground through 0 Ω; do not drive that net high with R9 fitted. Normal SWD programming does not require doing so.

The installed firmware starts I²C at 100 kHz, but MAX-M10S and AS7331 impose 300 ns rise-time limits. Do not apply a relaxed 1 µs limit just because the bus runs slowly. Total capacitance includes IC pins, traces, pads and any attached measurement leads. Check both lines at the farthest devices with a low-capacitance probe.

## Power follow-up

Keep C8/C21 and the regulator's local bypass capacitors. The TI output-capacitance table has a 10 µF minimum and 22 µF nominal value, while its application guidance recommends 22 µF for most applications. Nominal values and typical bias curves do not establish a worst-case effective value over voltage, tolerance and temperature.

The power review also identified a distant GNSS bypass capacitor, C10, and a ferrite bead whose specified maximum DC resistance exceeds u-blox's 0.2 Ω series-resistance guidance. These warrant a focused supply-layout and component review. They do not establish the cause of past flight GPS faults.

## Fabrication and routing style

The first copper cleanup checkpoint was PCB `4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54`. It widened the U8 landing and narrow ground contact, closed tiny U1/output/GND pockets, widened the U6 ground bridge, rounded electrical junctions and removed microscopic artwork specks. [Checkpoint proof](fabrication/final-independent.json), [before/after](fabrication/candidate/before-after.pdf).

The final RF revision preserves that cleanup and rounds its new routing. The original label shapes are retained, shifted upward 0.55/0.22 mm for the front guard. Editable text remains on F.Fab, grouped with its copper outlines. Green solder mask remains; no silkscreen is added. All 37 net-assigned copper graphics contact the same-net conductor network, with no orphan filler scraps.

Final full-copper screening includes pads, tracks, vias, filled zones and artwork on both faces. It reports zero candidates for:

- Acute gaps below 60°, with at least 0.075 mm edge support after 2 µm simplification.
- Copper tips below 30° under the same screening method.
- Enclosed gaps smaller than 0.02 mm² with inscribed diameter below 0.10 mm.
- Copper islands smaller than 0.01 mm².

These explicit thresholds detect the targeted etching concerns; they are not a claim that every possible process defect is ruled out. The strict project enforces 0.10 mm minimum connection/groove widths with error severity. JLC [layout guidance](https://jlcpcb.com/features/layout) also requires supplier review of acute-angle traps, annular rings and mask slivers. The 0.4 mm board still needs appropriate fabrication and handling.

Final native results: **0 DRC violations, 0 opens, 0 schematic mismatches, 0 unexcluded ERC findings**. The two documented ERC exclusions remain. The independent scope check permits only declared poses, pad connection modes, courtyard/model details, routing and artwork translations. It preserves the circuit, outline and physical pad identities.

## Evidence and reproducibility

- [Final native checks and visual review](rf/final/root-review.json)
- [Final pad/net/placement scope](digital/final-rf-scope.json)
- [Actual copper and ground reference](digital/final-rf-reference.json)
- [Final filled-copper screen](fabrication/final-rf-screen.json)
- [No orphan net-assigned graphics](fabrication/rf-final/orphan-screen.json)
- [C5 library comparison](digital/final-c5-library.json) and [GNSS model comparison](digital/final-gnss-library.json)
- [Native power topology check](power/rf-final-power.json) and [mechanical review](power/RF-MECHANICAL-REVIEW.md)
- [Front](rf/final/visual/top.png) and [rear](rf/final/visual/bottom.png) native renders, showing the full CAD including U6; the pilot omits U6
- [I²C, programming and UART review](digital/README.md)
- [Capacitor and power review](power/README.md)
- [Portable evidence verification](EVIDENCE.md)
- [Baseline hashes](baseline/manifest.json) and [original RF crossing](rf/rf-top-copper.png)

The canonical project file contained pre-existing edits disabling the mask-bridge check, setting mask-to-foreign-copper clearance to zero and restoring an obsolete LTR390 ERC exclusion. Those edits are recorded in `baseline/user-project.diff` and are preserved. Final native checks and the published package use the stricter project settings; do not confuse those settings with the current editor's overrides.

The saved JLC Y24 cart refers to the earlier hashed package. A CAD revision is not automatically reflected in that cart. Manufacturing exports, supplier review and physical RF/power qualification must match the chosen final revision.
