# Fully exposed v1.1 board

Teddy explicitly selected **no solder mask on either face** on 2026-10-12. This mask-only candidate starts from `41027a4a5115713016c49e61b76ecb4f4048da79`; integration of the VSTOR and diode changes is reviewed separately in the parent directory. It does not alter existing copper, component placement, drills, paste, labels, or zone fills.

Two locked, solid rectangles on F.Mask and B.Mask extend from (52, 28) to (78, 88) mm. They represent openings, with at least **1.305 mm** of overrun beyond the native board outline. Both faces, including the notches, solar contacts, traces, planes, vias, and pads, are therefore exposed. Full openings preserve this intent in native KiCad 3D and normal Gerber exports; omitting or blanking mask artwork would not express the same result.

Global front/back via tenting is off. Both nominal mask-film thicknesses are 0 mm. The nominal core entry changes from 0.31 to 0.33 mm to retain the 0.40 mm total with two 0.035 mm copper layers. This is a **stackup metadata selection**, not a measurement of existing flown boards or confirmation of a future fabricator stackup. Existing individual footprint/pad mask settings remain untouched because the full-face opening supersedes them. Copper surface finish is independent of solder mask and remains unspecified by this change.

## Verification

- [Scope and hashes](candidate.json): only PCB setup and the two mask rectangles differ. The schematic, project settings, libraries and every existing physical object are preserved.
- [Native checks](native-verification.json): all **232 physical pad connectivity sets** match, with zero opens. F/B copper polygons are exactly equal before/after; copper, paste, outline and drill exports are equal after removing generation timestamps.
- [Native and exported coverage](coverage.json): zero board area and zero copper area remains masked. All **143 front and 62 back copper polygon islands** are within the opening. Actual mask Gerbers have `FilePolarity,Negative`, a full opening region, and no subsequent clear-polarity operations that could restore mask. The [mask Gerbers](mask-gerbers.zip) are an audit subset, not an order package.
- Native KiCad 10.0.0 [front](native-bare-front.png) and [back](native-bare-back.png) renders show exposed copper. Display colors are illustrative, not a specification of surface finish. Existing purchased module models retain their own appearance.

## DRC disposition

The unchanged project produces **55 baseline findings** and **356 mask-candidate findings** in the saved verification run, both with zero opens and 11 existing schematic-parity findings. The difference is **297 `solder_mask_bridge` findings** and **4 `silk_over_copper` warnings**. An earlier run of the exact same source PCB/project produced 319 mask-bridge findings (378 total); source hashes, connectivity and exports remained unchanged. The precise representative count for this board-wide opening is therefore not a stable acceptance criterion. The raw [candidate DRC](candidate-drc.json) retains every finding from the saved run. The mask-only candidate does not change severities or exclude instances.

The mask bridges are the intended common opening across every net for a board manufactured without mask. They are not evidence of new copper connections. Any integrated project policy should explicitly identify the mask-bridge check as inapplicable to this chosen process and retain an audit run with the check enabled.

The four silk warnings are the existing two `GND` labels and two `+` labels. [Polygon measurements](silkscreen-review.json) find no label ink over any copper pad or any former pad opening. Nearest pad separation is about 0.337 mm for each `+`, 1.000 mm for the left `GND`, and 0.494 mm for the right `GND`. The left `+` is over substrate; portions of both `GND` labels and the right `+` are now over exposed copper. The full-board opening triggers the warnings because there is no mask under any label. Preserve and report these warnings; confirm which bare-board legend the fabricator can retain. The pad ring and copper clearances from the prior revision are unchanged, while its green-mask bridge requirement is superseded by the explicit no-mask process.

## Fabrication instruction

Specify **NO SOLDER MASK — BOTH SIDES; NO VIA TENTING** in the fabrication notes/order settings and confirm that CAM interprets the included F.Mask/B.Mask files as full-face openings. Keep solder-paste data for assembly; paste and mask serve different purposes. The full-open artwork is deliberate, not a missing mask layer. Surface finish and silkscreen retention remain separate fabrication choices. No files were ordered or uploaded in this task.

## Sources and reproduction

KiCad's official [PCB Editor manual](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html) was read in the in-app browser on 2026-10-12. Its graphical-item section defines mask layers as negative and shapes on them as openings. Its mask/paste section explains expansion and via tenting; the physical-stackup section explains thickness and visualization metadata. The native exporter independently confirms the opening polarity in the output, so this result does not rely solely on a visual preview.

From the repository root:

```sh
analysis/.venv/bin/python analysis/v1_1_bare_finish_20261012/mask/build_candidate.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_bare_finish_20261012/mask/verify_native.py
analysis/.venv/bin/python analysis/v1_1_bare_finish_20261012/mask/check_coverage.py
```

The builder writes only to `~/Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask`. For the displayed renders, copy the tracked `hardware/pcb/3d` directory into the scratch candidate, then use `kicad-cli pcb render --width 1000 --height 1800 --side top --zoom 0.78 --quality basic` and repeat with `--side bottom`. The candidate PCB SHA-256 is `35ebb51bba5fa2cf2760db6865276754bf8a75a0c8bdef4f4eb364838037f9c3`.
