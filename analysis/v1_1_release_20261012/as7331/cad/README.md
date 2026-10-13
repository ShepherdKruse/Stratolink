# AS7331 local CAD implementation

This directory owns the reproducible AS7331 circuit, footprint, schematic, and local routing candidate. The authoritative board stays in `hardware/pcb`; the candidate lives under `~/Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate`. These scripts do not promote or order hardware.

The accepted circuit uses AS7331-AQFM U6 (C20482877), two local 100 nF capacitors C14/C23 (C1525), and Vishay MCU0805MD3304BP500 R27 (C4313228), 3.3 MΩ, ±0.1%, 25 ppm/K. Address inputs A0/A1 and SYN are tied to ground for address 0x74 and command operation. READY is intentionally unconnected. Existing shared 4.7 kΩ bus pull-ups are retained. Pressure remains at 0x76. Analog and digital returns are joined locally. The UV channels require optical qualification and calibration before an ozone-column claim.

## Geometry and assembly basis

- The local symbol covers all 16 datasheet pins. The OLGA pin map uses the manufacturer's top-facing view, not an unmirrored bottom view.
- Package body is nominally 2.60 × 3.65 × 1.09 mm. Land centers follow the manufacturer contact locations. The chosen 0.35 mm square copper lands and 0.30 mm square paste apertures are an engineering-derived land pattern, not a claimed manufacturer-qualified stencil recommendation.
- The 0.30 mm square aperture has area ratio 0.75 with a 0.10 mm stencil; a 0.12 mm stencil gives 0.625. Use a 0.10 mm stencil or an assembler-approved local process for future U6 population. Initial pilots can omit only U6 while keeping both bypass capacitors and R27 fitted.
- U6 uses a generated project-local VRML model with nominal body, terminal layout, pin-1 mark, and a visible aperture marker. It is a visualization. The painted aperture is not a physical recess; optical analysis uses the separate primary-data 0.345 mm die recess.
- R27 uses the project-local standard KiCad 0805 STEP. U5 courtyard normalization and R27's conservative pad/body envelope are independently checked in `../review/propose_courtyards.py`.
- Current user-selected finish is green solder mask with no silkscreen. The independent finish patch is applied after routing. New via tenting is explicit on both faces; underbody vias must remain clear of lands and paste.

## Implementation tools

Use KiCad's bundled Python, not system Python, for the native board scripts:

```
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
```

`build_candidate.py` reconstructs the candidate from a protected source manifest, replaces the circuit and footprint, and performs only the enumerated local removals/placement changes. It supports an optional sibling scratch directory for isolated schematic review. `dump_geometry.py` exports native pad/track geometry. `route_candidate.py` is a conservative grid path proposer; its output is not signoff. `finalize_geometry.py` removes stale fill caches before loading the new copper, adds the verified rounded VSTOR path and local ground returns, and applies explicit via tenting. `freeze_new.py` preserves updated local footprint definitions.

KiCad can infer a new via's net from stale overlapping zone fills when loading a text-edited board. Therefore stale `filled_polygon` caches must be removed before native refill and net verification. Native DRC, freshly exported schematic netlist, retained physical-island comparison, source-hash verification, and independent review are required after final integration. Do not infer release status from any intermediate report in this directory.

## Local design scope

U6 and C14 are relocated to the northeast, C23/R27 are added, and C21 shifts left to clear the precision reference. C6 stays in its original location. Original nearby PB5 and VSTOR spans are rerouted at their original 0.25 mm width. Local I²C branches and ground stitches are rebuilt while retaining all shared bus connections. Ground return details include a short C12 spoke, a stitch for the R7/H2/R27 ground region, and local analog/digital bypass returns. The native board outline, GNSS RF feed, PA8, solar connectors and suspension geometry are outside this ECO.

The frozen electrical candidate is recorded in `pre-finish-manifest.json`. `pre-finish-drc.json` has zero errors, zero unconnected items, and zero schematic parity issues; its four warnings refer to the old solar silkscreen/full-board mask combination removed by the following finish step. `final-erc.json` has zero violations. These are electrical-stage results, not final manufacturing signoff.

`reproduce.py` records the exact scratch-only sequence, including the independently checked local-bus replacement, courtyard geometry, digital-ground bridge, and right analog-ground return. The protected pre-ECO source corresponds to repository HEAD `60c805edb8322487f2d4266d26b37169ff260efe`; after promotion the baseline manifest check intentionally prevents rebuilding over changed source. Use an isolated checkout of the matching baseline for historical reproduction. New KiCad-created child UUIDs may vary between rebuilds; compare native geometry and pin/net relationships, not byte hashes alone.

No global DRC thresholds or zone policies were relaxed. Both local ground necks use 0.125 mm copper where 0.15 mm could not clear the existing geometry; the retained board minimum is 0.10 mm. All new vias use 0.50 mm copper and 0.30 mm drill. The right analog-ground island returns around the front of the sensor to the already-grounded H2 annulus because the rear solar strip and front VSTOR route leave no legal through-via corridor. The extra return is visible and source-generated in `close_right_ground.py`.

The unchanged canonical source is protected by `baseline-source-hashes.json`; only the root release workflow may promote the reviewed files. Intermediate trials are not fabrication inputs.
