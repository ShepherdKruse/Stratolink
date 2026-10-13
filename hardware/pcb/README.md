# Stratolink hardware — v1.1 working revision

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. This is the canonical working project. Make subsequent v1.1 hardware changes here on `alpha/hardware-v1.1`, so the project Teddy reviews in KiCad stays current. Git preserves the earlier board revisions; the separate `../v1.1/` draft is superseded.

**Current finish: no solder mask on either face, with no via tenting.** The full-board F.Mask/B.Mask openings encode Teddy's exposed-board preference in the PCB, 3D view and fabrication artwork. Earlier green-mask checks below describe intermediate revisions and are superseded. Preserve stencil-paste data and specify no mask explicitly during CAM/order review; surface finish is a separate choice. [Current finish and assembly review](../../analysis/v1_1_bare_finish_20261012/README.md).

The first implemented change corrects U5's TMP117NAIYBGR DSBGA ball assignments and reroutes its local supply, ground and I²C connections. The precision sensor and existing C12 bypass stay in their original positions. The embedded schematic symbol and project-local reusable symbol are corrected together. The title block and copper revision label identify v1.1.

| Ball | Function | Connection |
| --- | --- | --- |
| A1 | SDA | SDA |
| A2 | SCL | SCL |
| B1 | V+ | +3.3 V |
| B2 | GND | GND |
| C1 | ADD0 | GND → address `0x48` |
| C2 | ALERT | GND; unused open-drain output, permitted by TI |

The new escape traces are 0.15 mm; four new vias use 0.60 mm copper / 0.30 mm drill. SDA uses a short back-layer crossover. C12 retains a local supply and ground path. That first repair preserved all 62 component placements and 239 pad geometries.

![Corrected temperature routing](../../analysis/v1_1_implementation_20261012/tmp117-routing.png)

The TMP117 correction's recorded verification passed independent symbol/netlist/copper checks and a refilled 0.15 mm clearance screen with no new local violations. See the linked change record for the exact checked revision and evidence. This is a working design, **not a manufacturing release**: inherited ERC/DRC findings and physical pilot validation remain open. The working project retains v1's rule settings, including disabled global clearance checks; use the recorded enabled diagnostic screen when assessing this repair.

- [Prioritized v1.1 / v2 checklist](TODO.md)
- [Promotion and fresh checks on this project](../../analysis/v1_1_implementation_20261012/promotion/README.md)
- [Change record, checks and native review views](../../analysis/v1_1_implementation_20261012/README.md)
- [Independent electrical review](../../analysis/v1_1_implementation_20261012/review/electrical_review.md)

The second change removes MK1 (T3902), its R20 clock resistor and C13 bypass capacitor, their dedicated signal routing, and the microphone's acoustic hole/mask/paste features. The remaining 59 footprints retain their placement. U2 pins 31/32 are explicitly unconnected. The shared 3.3 V supply through the former C13 location remains continuous. See the [microphone removal and verification record](../../analysis/v1_1_microphone_20261012/README.md).

Build `firmware/` with `platformio run -e stratolink_v1_1` for this no-microphone hardware. It leaves PB3/PB4 quiet and reports acoustic unavailable. The existing `stratolink` environment continues to support fitted microphones on v1 boards. No firmware has been flashed as part of this CAD change.

The third change replaces J1/J2 with direct-solder solar contacts: open unplated GND notches near the middle, with front/back lands and ordinary stitching vias, plus one 0.7 mm positive wire hole near each lower corner. Both panels remain parallel. The old side wire-support holes are removed; upper suspension holes, the 0.4 mm stackup, outside dimensions and all 57 other footprints remain. See the [attachment, thickness and cost study](../../analysis/v1_1_solar_attachments_20261012/README.md) and [front view](../../analysis/v1_1_solar_attachments_20261012/front-3d.png).

The mounting refinement now uses **1.0 mm-wide × 2.0 mm-deep** rounded cuts. The upper bank has GND copper on both PCB faces and one stitching via per side. This preserves existing signal routes while increasing nominal straight solderable bank overlap from **0.8 to 1.3 mm**. The lower positive holes remain 0.7 mm. All other components stay in place. [Dimension study, native checks and assembly procedure](../../analysis/v1_1_solar_attachments_20261012/qualification/README.md).

The solar contacts carry [photo-scaled panel, wire and solder models](3d/solar/README.md) in KiCad’s 3D Viewer: **94 × 75 mm** panels, 7 mm straight roots, gentle downward curves, and centered 0.5 mm solid positive wires with formed ends. A calibrated grid in ZachTek's product photo provides overall size; thickness, terminal preparation and strength still require the first physical assembly. This is a prototype CAD revision, with inherited fabrication findings and joint/RF/thermal checks still open. Use one or two verified pilots before the larger batch.

Keep the corrected `sym-lib-table`, `fp-lib-table` and `lib/` with the project. Custom 3D models remain local; standard models use KiCad 10's model directory. Other imported libraries still have inherited drift, so avoid a blanket update of every footprint from the library before those checklist items are reviewed.

The upper suspension corners now use **2.0 mm plated holes with 3.2 mm ground rings**, replacing the two 2.701 mm unplated outline cutouts at the same centers. H1/H2 are board-only mechanical footprints, excluded from BOM and placement, with no paste. The outline, 0.4 mm stackup, existing components and routing stay unchanged. This gives about one-third more FR4 ligament after nominal plating allowance; actual string wear and assembled strength remain physical checks. [Geometry, bridle loads, simulation and independent verification](../../analysis/v1_1_suspension_20261012/README.md).

An intermediate U7 correction changed its twelve local solder-mask margins to **0 mm instead of +0.102 mm** and reconciled its reusable footprint. Copper, paste and routing were preserved. The current full-board openings supersede those local mask settings and the intermediate green-mask dam requirement. ST's reduced stencil aperture recommendation and pilot solder-joint review remain open. [Historical U7 evidence and source limits](../../analysis/v1_1_fabrication_20261012/mask_u7/README.md) · [Historical combined verification](../../analysis/v1_1_fabrication_20261012/integration/README.md).

Ground now uses **one GND zone on both copper layers**, with the redundant back-layer zone removed. The zone-only consolidation produces identical copper. U7 pads 5/7/8 deliberately use their existing 0.20 mm ground traces, with local zone connection disabled; pads 3/6 retain their previous zone settings. These routes remain connected even in a diagnostic copy with every pour removed. J20's unsoldered Tag-Connect ground contact now has a solid zone connection. The two-spoke requirement, all routing, pad copper, mask, paste and drills were unchanged by that step. U7's project-local footprint carries the same layout-specific overrides; do not treat them as a generic ST land-pattern recommendation. At that checkpoint, project DRC had **57 findings, zero opens**, with the same 11 parity findings. The prior uniform-clearance screen had 70 findings; a stricter screen retaining original net-class clearances had 121. Neither had new finding signatures. [Decision, before/after copper and independent checks](../../analysis/v1_1_ground_20261012/README.md).

The near-edge +SOLAR, VSTOR and PA9 paths now clear the routed outline by at least **0.2336 mm** on all modified segments, with their 0.25 mm widths preserved. J3/J4's fourteen lands grow from 0.85 to **0.88 mm**, retaining the 0.50 mm holes and giving **0.19 mm nominal rings**. Their 1 mm pitch leaves approximately 0.12 mm copper spacing; the intermediate mask-web/color requirement is superseded by the current maskless finish. Separate local footprints match the placed left/right headers. All 232 physical-pad connected sets were preserved, with zero opens. At that checkpoint, project DRC had **55 findings**; the uniform diagnostic had 70 and the original-net-class diagnostic 110, both with all nine 0.20 mm edge findings removed. The stricter diagnostics retain explicitly assessed header-pad spacing findings. The original 0.50 mm edge policy and other release findings remain open. [Exact geometry and historical verification](../../analysis/v1_1_edges_20261012/README.md).

The current antenna assemblies now match Teddy's confirmed **straight enameled copper wires**. AE1 uses an 82 mm 915 MHz reference model and an envelope accommodating the documented 86 mm option; AE2 uses a 48 mm GNSS model. Dimensions are measured from the feed; wire diameter and solder tail remain nominal model assumptions. Incorrect spring/chip identifiers are removed from these two instances, with separate local footprints and models. The wire envelope clears D1 while preserving all antenna pads, feed locations and RF routes. The 0.0113 mm redundant VSTOR segment is also removed. Independent checks preserve all 232 connected pad sets with zero opens, and unchanged paste/outline/drills. Current project DRC still totals **55**: four old findings are removed and four warnings concern unchanged legends over the now-exposed surface. Only the inapplicable mask-bridge severity is disabled; a raw enabled audit is retained. [Combined evidence and native overview](../../analysis/v1_1_bare_finish_20261012/README.md) · [Fabrication intent](FABRICATION.md).
