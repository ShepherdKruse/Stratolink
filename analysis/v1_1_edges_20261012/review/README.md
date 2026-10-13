# Independent edge-route and component-hole review

**Scoped R2 review passed**, conditional on the solder-mask process below. Baseline `d70a53d`; frozen candidate `/Users/twarn/Repositories/ai-working/scratch/stratolink-edges-20261012/combined-r2`. PCB SHA-256: `c87926d6c121162258d936f6aa3e4cc3cc633ad249438340e551040a832d372a`.

The first combined candidate was rejected because pad growth created two unintended track-to-pad clearance regressions. The corrected candidate removes both. This is a bounded review of the requested edits, not whole-board production clearance.

## Actual scope and connectivity

The [approved inventory](approved-scope.json) and [verification](verification.json) establish exactly 12 segment endpoint edits, one added 0.25 mm segment, and 14 J3/J4 pad enlargements from 0.85 to 0.88 mm. Existing routed widths remain 0.25 mm. Hole diameters, centers, pad numbers/nets, footprint positions, outline, vias, retained zone settings and all unrelated board objects are unchanged.

All **232 physical-pad connectivity sets** remain identical after fresh native refill, including separate lands sharing a pin number. There are zero opens and no joins between previously disjoint pad groups. The project and library tables remain byte-identical. The schematic differs only in the J3/J4 Footprint property strings; the circuit is unchanged.

Two project-local left/right header footprints preserve their respective placed geometry instead of refreshing from a stock library. Their native pad geometry matches the board. All 80 previous project-library files remain exact; the only library additions are those two footprints. The inherited header Value text still mentions P2.54/D1mm, while actual geometry is P1.00/D0.50; this review uses actual pad geometry.

## Edge clearance: fabrication minimum versus saved policy

The [current JLC capability rows](../sources/jlc-capability-rows.json), captured from [JLC's capabilities page](https://jlcpcb.com/capabilities/pcb-capabilities), list 0.20 mm copper clearance to routed edges. Independent line-to-edge calculations use the actual slightly slanted outline segments and subtract half the unchanged track width.

| Changed route group | Minimum before | Minimum after |
|---|---:|---:|
| F.Cu +SOLAR | 0.139558 mm | 0.233673 mm |
| F.Cu VSTOR | 0.101731 mm | 0.251729 mm |
| B.Cu PA9 | 0.128734 mm | 0.233733 mm |

These are minima over the changed segment groups, including added transitions and adjacent integration corrections. They are not a claim that every track throughout the board has 0.23 mm margin. All nine findings in the 0.20 mm edge screen are gone. The two previously regressed pairs now measure **0.205000 mm** for J3.4 versus the long +SOLAR segment and **0.214411 mm** for J4.1 versus the VSTOR corner segment.

The saved project still specifies **0.50 mm** copper-to-edge clearance with that severity ignored. This repair does not meet a universal 0.50 mm policy, and the project rule was not silently lowered. Enabling only that saved edge policy produces **35 → 36 edge findings**: the new transition adds an object that also lies below 0.50 mm, while relocated traces improve but remain below that policy. The source-listed fabrication minimum and the saved project policy are separate constraints.

## Header rings, spacing and process condition

Native geometry and manufacturing exports agree on **0.880 mm pads, specified 0.500 mm finished holes and unchanged 1.000 mm pitch**. All 14 nominal minimum rings increase from **0.175 to 0.190 mm**. Both faces have minimum neighboring-pad clearance **0.119999 mm**, and minimum neighboring-mask web **0.119998 mm**. The minimum hole-edge distance to any foreign-net copper on either face is **0.309999 mm**. Actual mask exports have exactly the same 14 header flash coordinates per face, with aperture dimensions changed from 0.85 to 0.88 mm; every other mask graphic is identical.

For two-layer 1 oz copper, the captured JLC table lists a **0.18 mm absolute PTH-ring minimum** and **0.25 mm recommendation**, plus 0.10 mm conductor spacing and 0.28 mm PTH-to-track minimum. The selected geometry clears those listed minima. It does not reach the recommended ring: 1.00 mm pitch and unchanged 0.50 mm holes cannot accommodate a 0.25 mm ring while preserving conductor separation. A 0.90 mm pad would offer a 0.20 mm ring with only a 0.10 mm neighbor gap; 0.88 mm preserves additional gap. These are nominal CAD dimensions, not a guaranteed remaining annulus after drill registration, hole-size and etch variations.

**Mask-web acceptance is conditional:** the approximately 0.12 mm web meets JLC's listed 0.10 mm minimum for **1 oz green, red, yellow, blue or purple**, but falls below the listed **0.13 mm black/white** requirement. The candidate must not be described as compliant for every solder-mask color. The 1:1 mask aperture is supported by the captured process guidance.

The 0.12 mm pad gap deliberately falls below the stricter diagnostic 0.15/0.20 mm clearance targets. Exactly 11 adjacent different-net pairs are enumerated in the approved DRC inventory: J3 pins **1–2, 2–3, 3–4, 5–6, 6–7** and all six adjacent pairs on J4. J3 pins 4–5 share GND. The global project rules remain unchanged; none of these findings was hidden by reducing a rule or disabling a severity.

## DRC outcomes

| Fresh profile | Before | After | Interpretation |
|---|---:|---:|---|
| Saved project | 57 | 55 | Two header library mismatches removed; no new findings |
| Prior uniform 0.15 mm / edge 0.20 mm | 70 | 70 | Nine edge findings and two library mismatches removed; 11 named header pairs added |
| Retained net-class 0.20 mm / edge 0.20 mm | 121 | 110 | Nine edge findings, two library mismatches and 11 old header-gap signatures removed; only the 11 new 0.12 mm header-gap signatures added |
| Saved 0.50 mm edge policy enabled | 92 | 91 | Separate stricter policy audit; still 36 edge findings |

Every profile retains zero opens and 11 unchanged schematic-parity findings. The retained-net-class profile has **no added track-to-pad findings** in R2. Each added signature in the two clearance screens is compared against the explicit 11-pair inventory; a lower total count alone is not the acceptance criterion. Neither these counts nor unchanged connectivity establish whole-board manufacturing readiness.

## Copper and manufacturing outputs

The full copper unions were compared after fresh native fills. Front copper adds approximately **0.928937 mm²** and removes **0.706972 mm²**; back copper adds **0.714082 mm²** and removes **0.351770 mm²**. Intended differences lie in the reviewed edge/header neighborhoods, including local ground-fill changes. Raw remote union residues are retained in [geometry-verification.json](geometry-verification.json): about 0.000001803 mm² on F.Cu and 0.000002170 mm² on B.Cu. Their boundary displacements are bounded by **50 nm front / 2 nm back**. The larger remote corner difference seen in rejected R1 is absent from selected R2. These measured bounds describe native polygon/refill precision; no unscoped trace, pad or keepout edit occurred.

Front/back paste, board outline and both drill exports are **identical after timestamp normalization**. Front/back mask differences are confined to the 14 header apertures per face as described above. [Manufacturing exports](review-exports.zip) preserve both baseline and candidate. The two ring libraries and schematic links are intentionally local; no blanket library refresh occurred.

## Reproduction and preserved evidence

The [baseline manifest](baseline-manifest.json) pins 85 regular files, including all 80 old library files. Copied projects and DRC working directories are outside the repo under `/Users/twarn/Repositories/ai-working/scratch/stratolink-edges-20261012/review`. Baseline and candidate source hashes were checked unchanged after review.

Run [verify_native.py](verify_native.py) with KiCad's bundled Python and the frozen candidate directory, then [check_geometry.py](check_geometry.py) with `analysis/.venv/bin/python`. Native polygons are losslessly compressed in [native-geometry.json.gz](native-geometry.json.gz); [physical-connectivity.json](physical-connectivity.json) contains all 232 comparisons.

[Rejected R1 evidence](rejected-r1.zip) preserves the first candidate's DRC inventory, exact scope, polygons, geometry report, connectivity map and exports. Its two track-to-pad findings prompted the integration correction; its remote GND-corner plot belongs to that rejected version and must not be presented as selected R2 geometry.
