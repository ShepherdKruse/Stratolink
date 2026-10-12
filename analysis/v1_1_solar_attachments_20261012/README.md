# Side solar attachments and board trade study

2026-10-12. Working branch: `alpha/hardware-v1.1`. Baseline: microphone-removal commit `1aed52f`.

**Keep 0.4 mm FR4 and the current 23.36 × 57.30 mm outline for the v1.1 mounting revision. Develop the requested open ground notches near the middle, with separate positive wire holes lower down. A shorter 0.6 mm board belongs in a subsequent layout study.**

Teddy requested inner panel negative terminals soldered directly into the board's side cuts, with the outer positive terminals returning to one through-hole per side. Both panels remain parallel. This supersedes the prior proposal for positive contacts above ground wire anchors. The reference's visible shape is useful, but its inner terminal is positive; its electrical orientation is intentionally reversed here.

## Decision and cost

| Option | Outline | Modeled bare PCB mass | Current fifteen-board fabrication estimate | Implication |
|---|---|---:|---:|---|
| Retain v1.1 thin board | 23.36 × 57.30 mm | 1.255 g | $52.40 / $69.21 | Lowest disruption; preserve thickness and component placements |
| Thicker same outline | 23.36 × 57.30 mm, 0.6 mm | 1.753 g | $23.40 / $40.21 | Saves $29 per batch but adds ~0.50 g and changes RF stackup |
| Compact 0.6 mm target | 23.36 × ~40.9 mm | ~1.255 g under proportional copper assumption | $22.60 at default product category | Requires ~29% area reduction and substantial component repacking |
| Thicker same outline | 23.36 × 57.30 mm, 0.8 mm | 2.252 g | $23.40 at default product category | Adds ~1.00 g; no observed price benefit over 0.6 mm |

The two prices separated by `/` are JLC's default Industrial/Consumer electronics and Aerospace selections respectively. Aerospace automatically adds a four-wire Kelvin test. All are manual-dimension web estimates from October 12, excluding assembly, shipping and tax, with green two-layer FR4, 1 oz copper and ENIG 1 µin. No artwork was uploaded. A final manufacturer review can change cost or process eligibility. See [source captures and settings](sources/README.md), the [JLC quote](https://cart.jlcpcb.com/quote), and [JLC capabilities](https://jlcpcb.com/capabilities/pcb-capabilities).

These masses use the baseline's actual copper geometry and an assumed 1.9 g/cm³ FR4 density. They exclude solder, components, surface finish and attachment hardware. CAD specifies 0.4 mm; the delivered v1 thickness has not been verified against an order receipt or calipers. ±0.1 mm thickness sensitivity alone is about ±0.25 g at this outline. The thickness sweep remains pinned to the pre-mount baseline; the implemented mount was separately re-extracted below.

The main price reduction comes from changing thickness, not shrinking area: the compact 0.6 mm quote saves only another $0.80 across fifteen boards. The current component envelopes span over 52 mm, so shortening to 41 mm is a new layout. At 0.8 mm, equal baseline mass would require approximately 31.7 mm length, less than the retained capacitor's 34.5 mm maximum terminal envelope. [Full mass, outline, stiffness and material model](materials/README.md).

## Implemented in the canonical KiCad project

- Open **unplated** rounded notches at both side edges, centered at board y54.5 mm, close to the existing middle attachments. The candidate is 1.0 mm wide and 1.5 mm deep with a rounded inner end.
- Exposed GND copper on both board faces, set back 0.22 mm nominally from the notch wall (at least 0.2 mm from the outside edge), joined electrically with ordinary plated holes/vias. No plating is assumed on the notch wall. JLC's plated-edge/castellation process requires at least 0.6 mm material; the proposed unplated feature avoids relying on that process at 0.4 mm.
- Separate +SOLAR through-holes near the lower corners, one per panel, sharing the existing harvester input through a routed board connection. Candidate nominal finished drill 0.7 mm in a 1.4 mm copper land, suitable for screening 0.4–0.5 mm bare conductor with the published hole tolerance. The positive leads require insulation or controlled clearance from grounded panel terminals and the capacitor.
- Remove the two obsolete side copper-wire support openings. Keep the upper suspension openings, flat capacitor, pressure sensor and all other component placements.

The checked PCB, schematic and two project-local footprints are now installed in `hardware/pcb/`. The [promotion manifest](review/final/promotion.json) identifies the exact files. All 57 other footprints and 219 schematic nodes are unchanged; all 230 physical-pad connectivity comparisons pass. TMP117 correction and microphone removal remain intact. The project rules were preserved.

| Native check | Before | After |
|---|---:|---:|
| Project DRC findings | 73 | 70 |
| Enabled 0.15 mm clearance / 0.20 mm edge diagnostic | 87 | 83 |
| Unconnected items | 0 | 0 |
| Schematic parity findings | 11 | 11 |
| ERC findings | 55 | 55 |

The new attachments introduce no unexplained findings. Nine inherited edge warnings refer to the same copper against resegmented outer-edge lines; the comparison verifies unchanged copper and less than 0.001 mm line displacement. The remaining findings are still open, not waived. [Independent electrical and mass review](review/README.md), [raw DRC comparison](review/drc-comparison.json), [fabrication export review](fabrication/README.md), and [routing details](layout/IMPLEMENTED_CANDIDATE.md).

The final candidate bare-board mass is **1.2513 g versus 1.2546 g before**, effectively unchanged. This excludes solder, wires and panels and is not a measured saving. Both populated-board renderings were inspected: [front](front-3d.png), [rear](back-3d.png). They show the existing capacitor and components; the panels and their solder/lead envelopes are not modeled in those views.

The reference's contact is a crossed-sheet joint: the panel's terminal strip enters the side notch approximately perpendicular to the PCB. Seat its solderable face against a notch bank and join it to accessible front/back lands. A thin film centered in a 1 mm opening leaves a much larger unsupported solder gap. Actual film/terminal thickness, pre-tinning, solderable strip width, insertion depth and assembled angle are missing from the product drawing, so a physical dry-fit remains required before manufacture. The rounded tip leaves only about 1.0 mm of straight-bank insertion and 0.8 mm of nominal copper overlap at this provisional depth. See the [dimensioned joint section and tolerance model](mechanics/NOTCH_ASSEMBLY.md).

## What the mechanical model changes

A flexible wire from a lower board anchor to the panel's outer tip is an electrical lead, not automatically a weight-supporting tension brace. In the ideal pinned geometry it would need to carry **compression** to relieve the root moment. Increasing the vertical anchor spacing reduces that required compression, but bends, solder joints and panel curvature determine the real load path.

Two 90 mm bare copper leads weigh approximately **0.203 g at 0.4 mm diameter** or **0.317 g at 0.5 mm**. Their voltage drop is small at a panel's 50 mA nominal output; mechanical handling and insulation dominate selection. The idealized 70 mm panel span is a photo-based assumption, not a vendor dimension. It gives a root moment demand of 0.604 N·mm at 1 g and 3.02 N·mm at an illustrative 5 g. Neither value establishes joint capacity. [Mechanical, thermal and RF model](mechanics/README.md).

For an illustrative 30.5 mm run of 0.25 mm wide, 35 µm copper, room-temperature resistance is about 0.060 Ω, or 3 mV drop at 50 mA. That is a screening calculation for one added feed length, not the total harvester-input loss; final routed length, plating and temperature determine the exact value.

The panels and their leads are part of the RF environment. Moving the ground bond from the outer panel end to its inner end may change the antenna match and radiation pattern. Existing idealized NEC results show sensitivity but do not prove a penalty or an improvement for this assembly. Retest and retune the complete payload rather than treating its antenna wire in isolation.

## Before pilot manufacture

1. Measure both real terminal strips, including solder preparation; dry-fit the slot in an actual 0.4 mm sample and check iron access, panel angle and clearance to the rear capacitor and pressure vent.
2. Resolve or explicitly disposition the inherited fabrication findings on the final pilot revision. Native DRC, schematic parity, copper continuity and mask/drill comparison for this mounting change are recorded below; disabled project clearance checks are not evidence of clearance.
3. Compare weighed finished assemblies, joint deflection/foil peel after handling and thermal cycling, solar output while rotating, and installed RF/GNSS performance.
4. Confirm the fabrication category, stackup, finish and supplier acceptance of the unplated notch. Order the agreed small pilot quantity before the larger batch.

The [hardware checklist](../../hardware/pcb/TODO.md) separates CAD implementation from these physical checks. This study does not authorize an order or claim cold/altitude qualification.
