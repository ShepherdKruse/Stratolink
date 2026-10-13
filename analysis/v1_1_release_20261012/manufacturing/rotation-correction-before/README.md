# Manufacturing review package — not an order release

Source: `/Users/twarn/Repositories/Stratolink/hardware/pcb`
PCB SHA-256: `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15`

56 assembly references; BOM and CPL populations match. Explicit manual/DNP exclusions are in `assembly-audit.json`. Original native KiCad position CSV and netlist are under `native/`.

Order/process instructions: **NO SOLDER MASK ON EITHER FACE, NO VIA TENTING.** Both mask Gerbers contain whole-board openings with edge overrun; stackup mask thickness is zero. Do not interpret empty mask data as a no-mask instruction. Board nominal thickness is 0.4 mm. Confirm no-mask processing and finish in supplier CAM review. Preserve copper, paste, outline and separate plated/nonplated drills. Silkscreen exports retain source graphics. Any silk-over-exposed-copper advisories require supplier disposition; the baseline has four.

CPL: millimeters, absolute board coordinates, Y negated, X not mirrored on the bottom. Placement centers are placement-side SMD copper-pad bounding centers (not footprint graphics/text); U2's corner anchor needs a substantial center correction. Retained package centers and bottom rotation `(180-native_angle) mod 360` reproduce the prior shipped CPL. No component-specific rotation guess from a footprint filename is applied. For a new component the historical side convention is provisional and must be checked in supplier placement preview; new non-centered packages require explicit local Placement Offset X/Y metadata. See per-reference placement and rotation evidence.

No global paste reduction is performed. The F/B paste files are native source artwork, including any U7-specific change actually present in this candidate. Stencil thickness and any CAM-applied aperture reduction are supplier process decisions requiring the U5/U7 assembly review. Do not silently apply a second global reduction.

This generator does not qualify electrical operation, DRC exceptions, fabrication tolerances, new-part stock, supplier rotation libraries, or stencil process capability. It creates auditable files for review and performs no upload or order.
