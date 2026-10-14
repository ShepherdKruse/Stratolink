# Manufacturing review package for engineering review

Source: `/Users/twarn/Repositories/ai-working/worktrees/Stratolink/hardware-v1.1-review/hardware/pcb`
PCB SHA-256: `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`

57 assembly references; BOM and CPL populations match. Explicit manual/DNP exclusions are in `assembly-audit.json`. Original native KiCad position CSV and netlist are under `native/`.

Order/process instructions: **GREEN SOLDER MASK BOTH SIDES, ENIG, NO SILKSCREEN.** Selective mask openings expose component and solar soldering lands. Ordinary-via tenting and local apertures must match the reviewed native design; do not substitute automatic aperture expansion. Both legend Gerbers are deliberately empty because the native board and footprint artwork contain no silkscreen. Confirm preservation of the supplied mask geometry in supplier CAM review. Board nominal thickness is 0.4 mm. Preserve copper, paste, outline and separate plated/nonplated drills. Final supplier CAM acceptance remains pending.

CPL: millimeters, absolute board coordinates, Y negated, X not mirrored on the bottom. Placement centers are placement-side SMD copper-pad bounding centers (not footprint graphics/text); U2's corner anchor needs a substantial center correction. Retained package centers and bottom rotation `(180-native_angle) mod 360` reproduce the repository v1 production INPUT CPL, not a verified JLC post-CAM file. Supplier-model rotations require actual preview evidence for old and new parts alike. This export applies 5 explicit supplier rotation overrides; base/override angles, exact orderables, reasons and evidence are recorded in `assembly-audit.json` and the manifest. When supplied, the exact profile is copied to `supplier-rotation-profile.json`. It changes only CPL angles, not native CAD, centers, sides, population or BOM identity. No rotation is guessed from a footprint filename. New non-centered packages require explicit local Placement Offset X/Y metadata.

No global paste reduction is performed. The F/B paste geometry preserves the native design, including the U7-specific reduction, except for explicitly documented DNP pad omissions when a population profile is supplied. Stencil thickness and any CAM-applied aperture reduction are supplier process decisions requiring the U5/U7 assembly review and, for a future populated UV build, the AS7331 aperture review. Do not silently apply a second global reduction.

This generator does not qualify electrical operation, DRC exceptions, fabrication tolerances, new-part stock, supplier rotation libraries, or stencil process capability. It creates auditable files for review and performs no upload or order.

## Assembly population: v1.1 AS7331-layout pilot — U6 omitted, support circuit fitted

The native PCB and schematic describe the complete populated circuit. This pilot BOM/CPL intentionally omits U6. Exact part identities and reasons are in `population-profile.json`. Do not treat this pilot population as the complete design BOM. No UV measurements are available from a UV-DNP pilot.
Pilot F/B.Paste files deliberately omit the DNP pad apertures. The complete design paste remains under `native/full-design-paste/`; the export-only stencil PCB and its plots are under `native/stencil/`. `stencil-population-proof.json` records exact pad/layer omissions. Fabrication copper, mask, drills and outline still come directly from the complete canonical PCB. Never use this pilot stencil for a later fully populated UV build.
