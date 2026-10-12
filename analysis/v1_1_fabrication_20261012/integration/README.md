# Independent verification of integrated fabrication changes

**Pass**, 2026-10-12. The actual canonical `hardware/pcb` project was checked read-only after integrating the plated suspension pads and U7 mask correction. Its PCB SHA-256 is `268f5ef0f8d59caf0a46a0cb990fb26c1d74563e3423a15c16d361d392f9f96c`.

Compared with original checkpoint `a9d6ed5`, the only permitted changes are:

- H1/H2: two 2.0 mm plated holes with 3.2 mm grounded pads at the unchanged top centers; their previous circular Edge.Cuts cutouts are removed and GND fill is regenerated.
- U7: twelve explicit solder-mask margins change from +0.102 to 0.000 mm.
- Reusable libraries: one added suspension footprint and the reconciled U7 footprint. All other tracked library files remain byte-for-byte unchanged.

The independent checker confirmed that exact scope. All other PCB objects, schematic, project settings and library tables are unchanged. Zone configuration remains exact; only filled geometry changes for the suspension pads.

## Native electrical and manufacturing checks

- **232 physical-pad connectivity checks pass**: all 230 original pads retain their original logical connections after excluding H1/H2; each new mechanical pad reaches all 67 original GND nodes, with 69 GND nodes including H1/H2.
- All 879 straight tracks, three track arcs and 142 vias remain exact. Fifty-eight existing footprints remain exact; U7 differs only in its twelve mask settings.
- Project DRC: **70 → 61 findings**, with **0 unconnected / 11 parity**. Diagnostic 0.15 mm copper / 0.20 mm edge screen: **83 → 74**, also **0 / 11**. Only the eight U7 mask bridges and its library mismatch disappear; no new finding signatures.
- Fresh canonical Gerber exports match the independently checked suspension candidate's **front/back copper, front/back paste, back mask and Edge.Cuts**, apart from creation timestamps. Both plated and non-plated drill files are also unchanged.
- Front mask changes only two aperture definitions, used exclusively by the twelve U7 pad flashes. All flash coordinates and other plot commands are exact.
- Fresh project DRC ran against canonical CAD without saving it. Diagnostic overrides stayed in scratch. Hash guards confirm that no canonical file changed during this review.

[Full scope, connectivity, DRC deltas and hashes](verification.json) · [Project DRC](drc-project.json) · [Diagnostic DRC](drc-diagnostic.json) · [Fresh review exports](review-exports.zip)

## Limits retained

This is a prototype integration check, not a manufacturing release. The [U7 review](../mask_u7/README.md) records the selected JLC 1:1-mask process and the unresolved difference from ST's recommendation for a positively expanded opening, plus separate paste/land-pattern review. Existing whole-board fabrication findings remain. Suspension strength, string abrasion and assembled RF behavior still require physical testing.

The native script [verify_combined.py](verify_combined.py) reproduces these checks under KiCad's bundled Python. It is read-only for canonical CAD and writes diagnostic copies and export files only to scratch, with evidence here. Its baseline and accepted change scope are pinned deliberately; later PCB revisions need a new reviewed scope rather than silently broadening this check.
