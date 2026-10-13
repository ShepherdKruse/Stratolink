# Revision 2: header-compatible edge routing

This revision fixes the two real track-to-header regressions identified in the first combined candidate. The selected PCB includes the independently reviewed 0.88 mm J3/J4 lands. Every changed route now clears foreign header copper by at least **0.2030 mm**, based on native pad shapes and trace geometry, and every changed route remains at least **0.2336 mm** from the board edge.

Candidate: `/Users/twarn/Repositories/ai-working/scratch/stratolink-edges-20261012/routing/candidate-r2/stratolink.kicad_pcb`.

SHA-256: `c87926d6c121162258d936f6aa3e4cc3cc633ad249438340e551040a832d372a`.

The frozen first combined source `804094fbd6ba36ff1dce9fbbe0d9976d04e665df2e5612f2b2ada4805dcaae7e` and original routing-only source remain untouched. Canonical CAD was not edited by this task.

| Corrected clearance | First combined candidate | Revision 2 |
|---|---:|---:|
| VSTOR lower diagonal to square J4.1 corner | 0.1954 mm | 0.2144 mm |
| Long +SOLAR route to J3.4 | 0.1968 mm | 0.2050 mm, rounded |
| Minimum of all changed routes to any foreign J3/J4 copper | Below 0.20 mm | 0.2030 mm |

The +SOLAR vertical route moves **8.171 µm outward**, from x=53.683171 to x=53.675 mm. Its existing lower diagonal and upper transition are adjusted to preserve 45-degree routing and the complete path's outer endpoints. Its nominal edge gap becomes 0.2337 mm; the overlapping, unchanged x=53.650 mm feed remains as before.

The lower VSTOR bend moves **26.903 µm downward**, from y=69.723097 to y=69.750 mm. The short pad-entry horizontal extends to x=75.891 mm, preserving 45-degree routing around the corner and the pad-center endpoint. The side run remains x=76.299 mm, with 0.2517 mm board-edge clearance and 0.2030 mm spacing to J4.1. Moving only the side run would not have fixed the diagonal-to-corner clearance, which is why this revision checks complete pad and track shapes.

Relative to `d70a53d`, the final route patch modifies **12 existing segments** and adds **one transition segment**. All widths stay **0.25 mm**; layers and nets remain unchanged. The extra existing UUIDs compared with routing revision 1 are `e9b21ab4-de4f-4bb7-a599-94cd191c0bc8` (+SOLAR lower join) and `b6acae82-f692-4c92-8407-867053d1eac9` (VSTOR pad-entry horizontal). `build.json` provides the complete route-only inventory and final coordinates.

![Revised routing](routing-before-after.png)

All **232 physical pads** preserve their complete connected logical-pad sets against `d70a53d`; zero native opens remain. All nonroute objects, zone settings and boundaries, schematic, project, and local library files are exact matches to the frozen first combined candidate. The three complete modified paths preserve their outer endpoints. Existing dangling stub and courtyard findings are retained.

| Native check | `d70a53d` | Final combined r2 |
|---|---:|---:|
| Project DRC | 57 | 55 |
| Prior 0.15 mm spacing / 0.20 mm edge diagnostic | 70 | 70 |
| Retained 0.20 mm netclass / 0.20 mm edge diagnostic | 121 | 110 |
| Copper-edge findings | 9 | 0 |
| Unconnected items | 0 | 0 |
| Schematic-parity findings | 11 | 11 |

The two library mismatch removals come from the separate header-footprint update. The prior-screen total also includes **11 expected pad-to-pad 0.12 mm spacing findings** from the 0.88 mm lands on 1.00 mm pitch. In the retained-netclass screen, those pairs replace their previous 0.15 mm pad-to-pad clearance findings. All newly changed clearance pairs versus the original baseline are these header pad pairs; **none involves a routed track**. No diagnostic was relaxed to obtain this result. Full reports and raw deltas are retained in `native-review.json` and the three `candidate-r2-drc-*.json` files. This remains a bounded repair, not a whole-board clean-DRC claim.

Reproduce with `../build_candidate_r2.py`, KiCad Python `../verify_native_r2.py`, and analysis Python `../measure_and_plot.py --revision-r2`. The measurement script explicitly checks every changed segment against every foreign header pad on its layer, including rounded and square pad boundaries. `geometry-review.json` records all those distances, exact edge measurements, outer endpoint comparisons, and native full-copper deltas. Its copper comparison includes both header-ring and route changes versus `d70a53d`.

For route-only integration, use the 12 modified and one added segment blocks listed in `build.json`. This PCB already includes the frozen combined ring changes, so the parent may alternatively promote the entire independently rechecked combined candidate. Preserve schematic/project/library metadata when integrating only route blocks.
