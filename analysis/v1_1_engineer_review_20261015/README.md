# Engineer reroute review, 15 October 2026

The engineer-rerouted v1.1 board is retained, with bounded repairs to shorts, ground continuity, mask clearances, two copper pockets and GNSS ground reference. The schematic circuit is unchanged. This is the current engineering review revision; supplier placement preview, factory CAM and physical qualification remain outstanding.

Open the actual project in `hardware/pcb`, or use the complete [KiCad download](../../hardware/downloads/README.md). The original review ZIP remains in Downloads; its exact native files and ZIP hash are preserved in [intake](intake/intake.json). The review branch is [review/hardware-v1.1](https://github.com/Stratolink-hq/Stratolink/tree/review/hardware-v1.1).

## Changes added to the supplied layout

- Move two ground vias away from PA1 and PA9, removing two actual shorts. Make the other recorded local via and approach adjustments to meet copper clearances.
- Add two ground stitches to connect the U4/C11 ground section and the U1 ground section to the main plane. Remove nine isolated pours.
- Move C5 down **1.30 mm**, retaining its rear orientation and all three land sizes. This restores ground beneath the GNSS input without rerouting the antenna. All other 67 footprint poses are unchanged from the engineer's file.
- Replace U1's custom mask polygons with pad-based **0.04 mm** expansion. Set U4/L2 expansion to **0.05 mm**. Copper and paste lands are unchanged; measured foreign-copper clearances pass the current JLC screen. Move the right minus opening fully over ground.
- Remove a coincident GNSS segment and an unused 3.3 V via. Preserve the functional supply traces. Fill one tiny UV-zone corner void and shorten a redundant solar-feed tail/remove its loop beside L1 to open a trapped triangle.
- Restore schematic links on seven new footprints, retain manual-placement exclusions, and synchronize C5 courtyard, mask definitions and the AE2/L2 model entries in the reusable libraries. No component values, part numbers or pad nets changed.

Exact changes are in the [native ledgers](native/) and [repair scope](connectivity/repair-scope.json). Scripts beside this report document each local edit. Do not run them over the final board; their assertions target the preceding states.

## Verification

| Check | Result |
|---|---|
| Strict native KiCad 10 DRC | 0 violations, 0 open connections, 0 schematic mismatches |
| ERC | 0 unexcluded findings; existing U5 ALERT and U7 SA0 exclusions retained |
| Logical circuit | 66 exported components, 59 named nets, 247 pin/net/role entries unchanged |
| Physical mapping | 259 physical pads, 250 logical pad pairs; unchanged net assignments |
| Filled copper | No foreign-net overlap, disconnected assigned-net pads or assigned-net orphan islands |
| Footprint libraries | All 68 pad definitions and model transforms match the saved board |
| 3D assembly | All 63 model attachments resolve; panel, wire, capacitor and suspension geometry reviewed |
| Finish | 0.40 mm board, green mask, no silkscreen; manual solar and wire connections retained |

The [native summary](native/root-review.json) lists exact source hashes and the seven pre-existing ignored DRC categories. Clearance, mask bridge, annular and edge checks remain enabled. The incoming project had relaxed settings; the published review and exports use the prior strict project. The user's local editor project file is preserved, so locally saved editor overrides must not be mistaken for the published verification settings.

Independent reports: [connectivity](connectivity/README.md), [copper geometry](fabrication/README.md), [RF and power](rf-power/README.md), [mechanics and mask](mechanics/README.md). The source-bound evidence manifest is generated alongside the matching manufacturing package.

## What the checks do not establish

The GNSS path avoids switching copper and has a continuous rear reference beyond the antenna-pad transition. C10 is 2.87 mm from U3 VCC, versus 12.27 mm before the engineer reroute. The retained **0.75 mm** RF line is not qualified as a uniform 50 ohm line; finite ground geometry limits the simple impedance estimate. Compare assembled antenna match, GNSS C/N0 and LoRa coexistence on pilots. Converter ground is connected but has a local return detour; scope rail noise, startup and radio transients before attributing improvement to layout.

The copper screen retains twelve open electrical wedges, all reaching at least 0.10 mm width within 0.125 mm of the apex. They are connected to larger clearance regions, rather than isolated etch pockets. Small unchanged copper-logo fragments and two logo gaps remain documented. These quantitative screens are not an acid-trap or factory-etch guarantee. Ask CAM to assess the supplied artwork, fine-pitch lands and thin-board handling.

C5's maximum case clears the board and rear lands, but solder fillet/adhesive allowance and wire exit need physical inspection. The solar models are dimensioned assembly guides; actual foil thickness, wettable area, joint strength, wire gauge and bridle motion are still unmeasured. The wire antenna's nominal model exit has a small display penetration, not a measured manufactured interference.

## Manufacturing handoff

Initial population remains **U6 absent only**, with C14/C23/R27 fitted: 58 full-design / 57 pilot references. The pilot stencil must omit exactly U6's 16 apertures. Use matching [Gerbers, BOM and CPL](../../hardware/gerbers/v1.1-pilot/README.md), [fabrication intent](../../hardware/pcb/FABRICATION.md) and [checklist](../../hardware/pcb/TODO.md).

**The old JLC Y24 cart is stale.** U1 rotated and U8 moved to the front in this reroute. The [new CPL profile](manufacturing/rotation-review.md) is a draft until a fresh supplier preview confirms every placement on both faces. JLC sign-in is pending in the in-app browser. No current supplier DRC/CAM approval, new cart save, stock reservation, order or payment is claimed.

Primary references inspected for this review: [JLC PCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) and [TI RGR0020A package drawing](https://www.ti.com/lit/ml/qfnd242e/qfnd242e.pdf), retained under [sources](sources/). TI specifies 0.07 mm maximum NSMD expansion; the 0.04 mm U1 choice is within that bound. JLC's published green-mask screen is 0.09 mm to foreign copper and 0.10 mm web. Factory acceptance of the actual job remains required.
