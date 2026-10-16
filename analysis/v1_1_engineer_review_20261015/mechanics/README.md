# Mechanical, model and mask review

This review preserves the engineer's placement and routing. The current source identity is recorded in `models-pads.json`, `assembly-review.json` and `plotted-mask-review.json`. It is a native geometry and assembly review, not measured production qualification or supplier CAM approval.

All **68 embedded footprints** load from the updated project library. Their normalized pad geometry, drill sizes, local mask/paste settings and thermal settings match the library. All **63 model attachments** resolve with the project assets and KiCad 10 standard 3D library. Normalized model lists and transforms match all 68 local footprints. The AE2 library now retains the incoming 0.15 mm model Z offset, and L2 retains its previously embedded inductor model; these library-only changes do not move any board geometry. `library-source-identities.json` binds the final library bytes, including the later whitespace-only cleanup. J3/J4 programming lands, J20's Tag-Connect lands and H1/H2 suspension holes intentionally have no purchased-part 3D model. Both faces retain green mask; there are no silkscreen artwork items. The board remains nominally 0.4 mm, with the existing solar notches, suspension holes and programming features.

The STEP geometry was independently exported through KiCad to GLB and its mesh coordinates and placement transforms checked. AE2 is the **48 mm upward GNSS wire** at the engineer's top-left feed `(59.38, 33.13)` mm. AE1 is the **82 mm downward LoRa wire**. Their models retain the small solder tails. This confirms the files depict the intended wire directions and lengths; it does not establish radiation patterns or a measured wire diameter.

The nominal GNSS wire axis clears the modeled solar assembly by at least **20.54 mm** and conductive terminal metal by at least **21.21 mm**. The antenna hole retains **3.234 mm** of board-edge ligament. The mesh analysis includes the STEP solid's 0.1605 mm local axis offset, omitted from the earlier simple centerline calculation. For a symmetric triangular suspension, the string's XY projection crosses the GNSS wire for knot heights up to about **115.85 mm above the holes**. Keep the actual string behind the wire, with enough depth separation for its diameter and motion. A projected crossing alone is not a physical collision. Solar bend, film thickness, solder shapes and wire diameter are nominal display assumptions.

C5 is at `(64.875, 66.007)` mm, preserving the engineer's X coordinate and moving its terminals **1.30 mm down** to clear the rear GNSS feed reference. Its maximum datasheet case rectangle is X57.625–72.125/Y50.757–81.257 mm. It clears the board edge by **2.306 mm**, the lower antenna's rear copper land by **0.696 mm**, and the nearest Tag-Connect nonplated hole by **0.920 mm**. There is no projected case overlap with other rear lands. The other rear components are above the terminal area. Check the real capacitor, antenna solder fillet, insulation and attachment together; these distances do not include assembly placement error or an unmeasured solder envelope. The engineer's enlarged C5 courtyard is retained in the reusable footprint.

The U1 repair converts twenty custom perimeter mask polygons into native pad mask apertures with **+0.04 mm expansion**. Copper, paste, pad geometry, clearances, routing, exposed-pad mask and thermal holes remain unchanged. TI's RGR0020A drawing specifies 0.07 mm maximum around the preferred nonsolder-mask-defined land. The old polygon opening was larger, so the new opening is intentionally narrower, not claimed geometrically identical. U4 and L2 use the separately reviewed +0.05 mm mask margin.

Actual exported mask Gerbers were checked against same-revision copper. All 30 affected lands remain fully exposed:

| Part | Minimum aperture to foreign copper | Minimum web to another aperture |
|---|---:|---:|
| U1 perimeter | 0.1100 mm | 0.1800 mm |
| U4 | 0.1005 mm | 0.5966 mm |
| L2 | 0.1000 mm | 0.5200 mm |

These meet the review's 0.09 mm foreign-copper and 0.10 mm mask-web checks. Rounded native polygons are tessellated, so the U1 rounded-edge minimum measures 38.53 µm while its straight-edge mask expansion is 40 µm. Final mask registration and tent integrity remain fabrication checks. The generic rule is scoped here to these repaired apertures, not substituted for the board's documented fine-pitch exceptions.

The prior supplier rotation profile contains absolute angles tied to the old placement. U1's native rear orientation changed by 180°, U8 moved from the rear to the front, and U5 rotated 180°. They require renewed placement review; do not reuse old absolute overrides. U2/U4/U7 retained their native poses. U6 is still the only pilot omission; its new 180° orientation must be checked separately before any populated UV build. Keep C14/C23/R27 fitted and remove U6's sixteen paste apertures in the pilot stencil. J1/J2/J20 no longer carry the old exclude-from-position bit in the incoming file; the explicit manual assembly exclusions remain necessary.

[Full assembly](visual/assembly.png), [front](visual/top.png), [rear](visual/bottom.png). These native renders show the full design including U6. The initial three assembled pilots omit U6.

## Reproduce

Run native extraction under KiCad's Python and geometric calculations under `analysis/.venv/bin/python`. Paths are positional or explicit arguments; generated working files can stay outside the repository.

```sh
KICAD_PY native_audit.py PROJECT_DIRECTORY models-pads.json
KICAD_PY compare_libraries.py PROJECT_DIRECTORY library-pad-comparison.json
KICAD_PY compare_model_transforms.py PROJECT_DIRECTORY model-transform-comparison.json
KICAD_PY REPOSITORY/analysis/v1_1_peer_review_20261014/power/snapshot_assembly.py PROJECT_DIRECTORY/stratolink.kicad_pcb final-native.json
ANALYSIS_PY check_assembly.py --repo REPOSITORY --native final-native.json --output OUTPUT_DIRECTORY
kicad-cli pcb export gerbers --layers F.Mask,B.Mask --output SCRATCH_MASK_DIRECTORY/ PROJECT_DIRECTORY/stratolink.kicad_pcb
KICAD_PY extract_mask_audit.py PROJECT_DIRECTORY SCRATCH_MASK_DIRECTORY
ANALYSIS_PY check_plotted_mask.py SCRATCH_MASK_DIRECTORY plotted-mask-review.json
kicad-cli pcb export glb --no-board-body --component-filter AE1,AE2 --output antenna-models.glb PROJECT_DIRECTORY/stratolink.kicad_pcb
ANALYSIS_PY check_model_mesh.py antenna-models.glb antenna-model-mesh-review.json PROJECT_DIRECTORY/stratolink.kicad_pcb
```

`patch_u1_mask.py ORIGINAL_PROJECT NEW_SCRATCH_PROJECT` reproduces the U1-only mask repair on an unpatched source. It copies the project to a new scratch directory, preserves copper and paste, and emits its ledger. Do not run it on the already repaired board.

`sync_library_models.py PROJECT_DIRECTORY REPORT.json` reproduces the bounded AE2/L2 library model synchronization; run the normalized comparison afterward. It does not alter the PCB.

`render-review.json` records the exact final renderer arguments, source hash and image hashes. The evidence files are read-only reviews of the source; none are an instruction to replace the engineer's layout.
