# Ground-zone cleanup audit

2026-10-12 · baseline `c3d70a4` · canonical PCB hash `268f5ef0…` · scratch only.

**Remove the redundant B.Cu-only GND zone `e9b71a22-0a8a-41f9-b5c4-115945b7ef58`, retaining the existing F.Cu/B.Cu GND zone and the rule area.** After native refill, both the complete copper and GND fill alone are geometrically identical on each layer. This removes the overlapping-zone error without changing return paths, routes, pads or zone parameters.

## Why the zones are redundant

| Native zone | Layers | Baseline filled area | Settings |
| --- | --- | --- | --- |
| `795c4093-4930-4bcb-9c07-8e31d04084fe` | F.Cu, B.Cu | F: 357.378159 mm²; B: 0 | GND, priority 0, clearance 0.5 mm, minimum fill 0.25 mm, thermal gap/spoke width 0.5/0.5 mm |
| `e9b71a22-0a8a-41f9-b5c4-115945b7ef58` | B.Cu | B: 583.718316 mm² | Identical settings |

Both polygon boundaries are quadrilaterals extending outside the board. Their raw vertices differ, but their effective board coverage is the same. The overlapping back zones share priority 0, producing KiCad's zone-intersection error. The existing two-layer zone already supplies front copper; after the duplicate back zone is removed, it supplies exactly the same back copper as well.

The rule area `5d0fa8ee-3d1d-47e3-9c6e-f4062953791d` remains exact. It spans both copper layers near the upper power circuitry and excludes copper pours while allowing tracks, vias and pads. No keepout, island-removal setting, clearance, thermal parameter, priority or retained zone boundary was changed.

## Two evaluated variants

| Variant | Change | Native copper result | Recommendation |
| --- | --- | --- | --- |
| `single-two-layer` | Delete only the duplicate B.Cu zone | Exact equality on both layers | Selected: one shared GND zone is sufficient |
| `front-only-main` | Restrict `795c…` to F.Cu and keep `e9b…` on B.Cu | Exact equality on both layers | Also valid if separate zone objects are desired |

Selected scratch PCB:
`/Users/twarn/Repositories/ai-working/scratch/stratolink-zones-20261012/zone/single-two-layer/stratolink.kicad_pcb`

SHA-256: `ab6190a1a7b7fc2b79976c282bd1074151ad8b0cc5834413b6b48b1058f91bb4`.

The alternative hash is `2bf30c00293138b04fdc22218be3d358cac8c888bd4229ddfcf2321a763b7c78`. Neither variant was promoted by this audit. Both retain the untouched schematic, project settings and local libraries in their scratch folders.

## Return-path and regression evidence

The complete native copper union is **663.930702 mm² on F.Cu and 816.707485 mm² on B.Cu**, before and after. Both layer comparisons have exactly **0 mm² added and 0 mm² removed**. Separate comparisons of filled GND polygons also have exact geometric equality. There are no changed copper regions or narrowed ground paths to qualify in this zone-only change. This is a representation cleanup, not an RF or ground-performance improvement claim.

- Every non-zone PCB object is exactly equal as a parsed object, including all footprints, pads, tracks, vias, outline geometry, mask changes and model references.
- All **232 physical pads** retain exactly the same connected logical-node sets. All **228 logical pad nodes** and net names are unchanged; native opens remain **0**.
- Schematic and project files are byte-identical.
- Project DRC: **61 → 60**. Enabled 0.15 mm copper / 0.20 mm edge diagnostic: **74 → 73**. In both screens, the only removed finding is `zones_intersect`; no finding is added. Schematic parity remains **11**.
- The three pre-existing thermal warnings are deliberately unchanged by the zone-only candidate. They are addressed separately in the parent task.

[Native scope/connectivity/DRC review](native-review.json) · [complete and GND-only copper comparison](copper-comparison.json) · [candidate hashes](build.json).

Reproduce scratch variants with [build_candidates.py](build_candidates.py), then run [native_review.py](native_review.py) using KiCad's bundled Python and [compare_copper.py](compare_copper.py) using `analysis/.venv/bin/python`. The diagnostic copies enable clearance, annular-width and copper-edge reporting at 0.15/0.20 mm without altering either candidate's project configuration. The baseline and candidate fills use their actual project settings; the independent diagnostic refill is kept in separate scratch folders. Native geometry is retained here as `native_geometry.json.gz` with source hashes and raw DRC reports; verbose command logs stay in scratch.
