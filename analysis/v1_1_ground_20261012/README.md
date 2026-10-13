# Ground zones and local pad connections

This scoped v1.1 change starts at `c3d70a4` on `alpha/hardware-v1.1`. The canonical project is `hardware/pcb/stratolink.kicad_pro`. It clears the duplicate-zone finding and three starved thermals while preserving the working circuit, routing and component placement. It does not close the remaining fabrication or U7 assembly-pattern checklist items.

## Selected changes

| Object | Change | Reason |
| --- | --- | --- |
| Main GND zone | Keep one zone covering F.Cu/B.Cu; delete redundant B.Cu zone `e9b71a22…` | Both consolidation options produce exactly the same complete copper and filled-zone polygons as the baseline. One shared definition removes the overlap. |
| U7.5, U7.7, U7.8 | Explicit `zone_connect 0`; retain every existing ground trace | Declare the existing trace returns intentionally and remove nearby pour fragments that cannot support the requested relief geometry. |
| U7.3, U7.6 | Keep existing settings | Pad 6 retains its existing pour neck and connection to the nearby stitching via. |
| J20.5 | Explicit `zone_connect 2` (solid) | Tag-Connect uses an unsoldered spring contact; a soldering thermal relief is unnecessary at this pad. |
| Project-local U7 footprint | Same three pad overrides | Keep this layout's reusable footprint consistent without refreshing unrelated imported footprints. These settings are specific to the existing routed board. |

U7 is the LIS2DH12 accelerometer. The repaired TMP117 is U5 and is unchanged here. The upper two-layer copper-pour keepout, solar/suspension geometry, 0.4 mm stackup, all 61 footprints, 232 physical pads, 882 routed track/arc objects and 142 vias are preserved. No schematic or project-rule edit is needed.

## Why this connection strategy

The original zone requests 0.5 mm relief gaps and 0.5 mm spokes around U7 lands only 0.35/0.45 mm across. Local smaller-gap/spoke and angle trials could remove a warning by eliminating a pour contact, or move the single-spoke condition to the neighboring pad. A missing warning did not establish two useful relief spokes.

The chosen design makes the actual intended connection explicit. In an isolated native diagnostic with every zone removed, all five U7 GND pads still reach C19.1, C21.1, R5.2 and two ground vias through existing 0.20 mm traces. The final filled board must also preserve the full original ground network. The [trace-path audit](review/trace-grounding/README.md) records the route UUIDs and a nominal DC sanity check; it does not claim RF impedance or reflow qualification.

Disabling zone contact on only pads 5/8 shifted the warning to pad 7. Disabling it on all five grounds created a dangling-via finding by removing pad 6's useful pour neck. The selected 5/7/8 set avoids both problems. The global minimum remains **two resolved thermal spokes** wherever thermal relief is selected. None of the three trace-fed pads is described as having a repaired two-spoke relief.

J20.5 remains the same 0.7874 mm contact with no paste. Its solid connection preserves contact geometry and guide holes; it does not solve mechanical retention of the programming cable. [Primary sources and interpretation](sources/README.md).

## Verification

| Check | Baseline | Revised |
| --- | ---: | ---: |
| Native project DRC findings | 61 | 57 |
| Previous diagnostic: 0.15 mm clearance assigned to every net class, 0.20 mm copper-edge | 74 | 70 |
| Stricter diagnostic: original net-class clearances retained, 0.15 mm global minimum, 0.20 mm copper-edge | 125 | 121 |
| Unconnected items | 0 | 0 |
| Schematic/PCB parity findings | 11 | 11 |
| Physical-pad connectivity comparisons | — | 232 unchanged |

The four removed signatures are exactly the zone overlap and original U7.5, U7.8 and J20.5 starved thermals. There are no new finding signatures in either diagnostic. Remaining project findings are 55 inherited library mismatches, the D1/antenna courtyard conflict and the VSTOR stub. The prior diagnostic adds four clearance and nine copper-edge findings; the stricter diagnostic adds 55 clearance and nine copper-edge findings. The different totals result from different net-class rules, not a board regression. Component-hole annuli remain a separate fabrication-review item.

Independent review compares Git-pinned regular library snapshots, every board object and physical-pad connected set, actual copper polygons, and native manufacturing exports. Front/back mask, front/back paste, outline and both drill files are identical after timestamp normalization. The project's original global clearance severities are unchanged; the separately enabled diagnostic prevents those disabled settings from concealing a regression.

The complete B.Cu union is exactly unchanged. On F.Cu, U7 loses approximately 0.075892 mm² and J20 gains 0.525221 mm². Outside those reviewed neighborhoods, the raw difference is 0.000000892 mm², entirely within a 2 nm polygon-boundary buffer; this numerical residue is recorded rather than presented as exact front-copper equality. Under U7's nominal 2 × 2 mm body, total copper falls from 2.533979 to 2.458207 mm². Fixed traces and pad metal remain beneath the body; this is not proof of ST land-pattern conformity or a reflow-temperature model.

![Native U7 copper before and after](review/U7-zone-contacts.png)

- [Independent review and copper comparison](review/README.md)
- [Native verification](review/verification.json)
- [Zone-only exact copper comparison](zones/README.md)
- [Thermal trials and rejected alternatives](thermals/README.md)
- [Review manufacturing exports](review/review-exports.zip) — inspection artifacts, not an order package
- [Current hardware checklist](../../hardware/pcb/TODO.md)

## Reproduction and promotion

Run `analysis/.venv/bin/python analysis/v1_1_ground_20261012/build_candidate.py` from the repository. It reconstructs the candidate from the pinned baseline under `~/Repositories/ai-working/scratch/stratolink-zones-20261012/combined`; it never writes canonical CAD. `candidate.json` records exact hashes. The independent reviewer has separate native and geometry checks documented in its report.

Only the checked PCB and U7 library footprint are promoted to `hardware/pcb`. `before.json` guards the baseline CAD and 100 unrelated tracked local changes. `promotion.json` records the final canonical hashes, fresh DRC, and preservation check. No firmware, component order, remote push or fabrication release is part of this step. Physical pilot validation and ST land/mask/stencil conformity remain open.
