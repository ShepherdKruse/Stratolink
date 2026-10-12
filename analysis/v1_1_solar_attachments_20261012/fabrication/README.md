# Independent fabrication export review

2026-10-12. **Pass for the intended fabrication geometry**, on candidate PCB SHA-256 `e502e2735535fe525f9699972b2be0dfbc038ae7773fc8da4003339f8e522ba0`. The candidate files remained unchanged throughout the read-only review. This is not a manufacturing release or mechanical fit qualification.

The [review script](check_exports.py) loaded the actual candidate with KiCad 10.0.0 and exported Gerbers, separate PTH/NPTH Excellon drill files and maps, native copper/mask SVGs, and a read-only DRC report. Export files remain in `/Users/twarn/Repositories/ai-working/scratch/stratolink-solar-fab-review`; their hashes and source hashes are recorded in [evidence.json](evidence.json).

Verified:

- KiCad constructs one valid board outline. Each side notch is an open void with retained upper/lower banks and laminate beyond the inward tip. The exported `Edge_Cuts.gm1` identifies the profile as **non-plated** and contains both exact R0.5 mm notch arcs. The notch is not a plated slot or an oval drill instruction.
- J1/J2 each have a +SOLAR **0.7 mm round plated hole** at `(75.2, 85.0)` and `(54.8, 85.0)` mm. Both appear in the PTH drill export.
- Four **0.3 mm ordinary plated GND vias** appear in the PTH export: `(54.1665,53.45)`, `(54.1665,55.55)`, `(75.8255,53.45)` and `(75.8255,55.55)` mm. Excellon coordinates round to 0.001 mm, so the exact-match screen allows ±0.00051 mm coordinate quantization. Front/back ground connectivity is checked separately by the independent electrical review.
- The export contains **167 PTH and 3 NPTH drill hits**, with no Excellon slot commands. The three NPTH hits belong to the retained service footprint; routed suspension holes and open notches are profile geometry rather than NPTH drill hits.
- J1/J2 custom surface GND lands have no drilled holes; `drilled_hole_plated` is explicitly null for them in the evidence. **Their adjacent routed notch walls remain unplated.**
- No J1/J2 pad or graphic occupies F.Paste/B.Paste, and neither reference appears as a component/pad aperture in the exported paste Gerbers. Native front and rear mask SVGs visibly expose the two U-shaped ground lands and round positive-hole lands.
- No J1/J2 courtyard overlap appears in native DRC. Because the inherited project disables its PTH-inside-courtyard rule, the script also explicitly checks the new drilled pad envelopes against all other native front/back courtyard polygons: **zero overlaps**.
- Native DRC has **zero unconnected items**. It still reports 70 other findings (13 errors, 57 warnings) and 11 schematic-parity findings; the separate layout baseline comparison controls which are inherited. This review does not waive those findings or describe the whole board as DRC-clean.

Native front-copper/outline and both mask plots were visually inspected. No missing side opening, accidentally masked anchor or remaining old header pad was observed.

## Nearby component clearance screen

The native footprint drawing bounds provide the following conservative 2D distances from the ground-land pad envelopes. These include drawing-line width and are **not assembled 3D clearance measurements**:

| Feature | Left J2 ground land | Right J1 ground land |
|---|---:|---:|
| C5 rear body drawing | 2.209 mm | 2.451 mm |
| C5 rear courtyard drawing | 1.209 mm | 1.451 mm |
| U4 pressure-sensor body drawing | 13.470 mm | 1.806 mm |
| U4 front courtyard drawing | 13.272 mm | 1.222 mm |

The actual polymer panel, solder fillets, insulated wire bends, capacitor pouch variation and iron access are absent from those CAD envelopes. Their clearance and the pressure-sensor vent access remain physical mockup checks. The [crossed-sheet assembly review](../mechanics/NOTCH_ASSEMBLY.md) defines the slot-fit and wetting measurements required before ordering.

## Reproduce

Run with KiCad's bundled Python:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_solar_attachments_20261012/fabrication/check_exports.py
```

The script defaults to the frozen scratch candidate and a separate export directory. `--candidate` and `--output` can point to another exact source and fresh output location. It neither refills nor saves the source board, and it rejects a source-hash change during review.

The exact checked export files are retained in [review-exports.zip](review-exports.zip), with [archive and member hashes](archive-manifest.json). They are diagnostic review files, not an approved JLC order package.
