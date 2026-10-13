# Component-hole annulus audit — 2026-10-12

Enlarge all **14 J3/J4 copper lands from 0.85 to 0.88 mm**, keeping every **0.50 mm hole, center, pad shape, net and route unchanged**. This gives a **0.19 mm minimum annulus** and approximately **0.12 mm adjacent copper/mask gap**. The selected annulus is above JLC's **0.18 mm absolute PTH minimum** and below its **0.25 mm recommendation**; it is a constrained improvement, not achievement of the recommended ring size. Source: [captured JLC capability rows](../sources/jlc-capability-rows.json).

The frozen standalone candidate is `/Users/twarn/Repositories/ai-working/scratch/stratolink-edges-20261012/rings/pad0p88`, PCB SHA-256 `194705abb2dc3151d6cf067892d350fda43a495820eb89e202c78e2a616d5ec1`. Baseline is `d70a53d2093454084c9b1ae989d0276a88395334`. This standalone candidate is historical ring-only evidence. The final integrated candidate is `/Users/twarn/Repositories/ai-working/scratch/stratolink-edges-20261012/combined-r2`, PCB SHA-256 `c87926d6c121162258d936f6aa3e4cc3cc633ad249438340e551040a832d372a`. Use the [final combined review](../review/README.md) and [revision 2 routing report](../routing/r2/README.md) for integration results.

## Geometry and choice

J3/J4 are physically **1.00 mm pitch**. A 1.00 mm land with the existing 0.50 mm hole would achieve the recommended 0.25 mm ring but **touch adjacent lands on different nets**. It is therefore infeasible without changing hole pitch or hole size.

| Land size | Minimum annulus | Minimum adjacent gap | Minimum drill-to-foreign copper | Decision |
| --- | ---: | ---: | ---: | --- |
| Existing 0.85 mm | 0.175 mm | 0.149999 mm | 0.324999 mm | Nominal ring is 0.005 mm below the current PTH absolute minimum. |
| **Selected 0.88 mm** | **0.190 mm** | **0.119999 mm** | **0.309999 mm** | Balances ring and separation margins. |
| 0.90 mm | 0.200 mm | 0.099999 mm | 0.299999 mm | Approximately at the 0.10 mm mask/spacing minimum; reduces routing margin further. |
| 1.00 mm | 0.250 mm | 0 mm | 0.249999 mm | Adjacent different-net lands touch; reject. |

Pad 1 remains square; pads 2–7 retain their equal-axis oval shape, which is geometrically circular. The minimum ring for these centered holes is half the smaller land dimension minus half the hole diameter; the square's larger diagonal ring does not substitute for its narrower side ring.

Current mask expansion is zero. The selected aperture therefore grows with the copper to 0.88 mm on both faces; no mask is pulled back over the ring. The resulting approximately 0.12 mm web is supported by the sourced JLC **1 oz green, red, yellow, blue or purple** mask limit of **0.10 mm**, leaving approximately 0.02 mm nominal margin. It does **not** meet the sourced **black/white 0.13 mm** minimum. This mask-color condition is part of the selected geometry's fabrication assumptions. The existing PTH pads have no paste aperture. The 0.50 mm finished holes and their locations are preserved, so mating fit is unchanged from v1. No actual connector manufacturer/pin specification is recorded here, so this does not certify a newly selected mating header.

[Geometry audit](geometry-audit.json) checks both faces. Before the separate edge reroute, the selected header land-to-outline minimum is 0.68873 mm, mask-to-foreign-track minimum is 0.19539 mm, and drill-to-foreign-copper minimum is 0.309999 mm. The last exceeds the cited 0.28 mm PTH-to-foreign-copper requirement. These measurements use all neighboring pads/tracks/vias, preserve the square pad corners, and exclude same-net copper. Polygon approximation is recorded in the evidence.

## Complete PTH inventory

The board has **25 PTH pads encoded inside footprints**, plus **142 ordinary vias**:

| Items | Count | Copper / hole | Nominal minimum ring | Interpretation |
| --- | ---: | --- | ---: | --- |
| J3/J4 | 14 | 0.85 / 0.50 mm → 0.88 / 0.50 mm | 0.175 → 0.190 mm | Selected component/wire-hole correction. |
| AE1/AE2 | 2 | 1.50 / 1.00 mm | 0.250 mm | Antenna wire lands; unchanged. |
| J1/J2 positive solar leads | 2 | 1.40 / 0.70 mm | 0.350 mm | Already replaced in the solar-mount revision; unchanged. |
| H1/H2 suspension holes | 2 | 3.20 / 2.00 mm | 0.600 mm | Grounded structure holes; unchanged. |
| U1.22–26 | 5 | 0.50 / 0.30 mm | 0.100 mm | BQ25570 thermal vias encoded as PTH pads, not inserted component lead holes. |
| Ordinary PCB vias | 142 | 0.60 / 0.30 mm | 0.150 mm | Apply the via fabrication rule rather than the component-PTH rule. |

U1's thermal-via process and paste/mask treatment remain a separate package/fabrication review; relabeling these as component leads and mechanically enlarging them is not justified. All 25 PTH pad UUIDs, layers, shapes, offsets and nets are in [the inventory](geometry-audit.json). The selected 14 UUIDs and exact before/after changes are in [verification.json](verification.json).

## Scope, libraries and native checks

The two new project-local footprints are derived independently from the placed J3/J4 geometry, preserving their small existing coordinate differences:

- `lib:Stratolink_Header_Left_1x07_P1p00_D0p50_Pad0p88`
- `lib:Stratolink_Header_Right_1x07_P1p00_D0p50_Pad0p88`

Only their 14 pad sizes, PCB footprint identities and the two schematic `Footprint` properties change, plus regenerated zone fill. All 80 baseline library files remain byte-identical. The superseded shared trial footprint was removed; no stock-library edit or blanket footprint refresh occurred. The preexisting misleading `P2.54mm...D1mm` component Value/Description text remains unchanged and should be corrected separately once the actual connection intent is settled.

[Native verification](verification.json) proves **232 unchanged physical pad connectivity sets**, zero opens, unchanged hole centers/drill dimensions/shapes, and exact schematic/project scope. Project DRC is **55 vs 57**, removing only the two old J3/J4 library mismatches; the existing 11 parity findings remain. The uniform **0.15 mm** diagnostic is **79 vs 70**: it removes those two library mismatches and adds **11 header-adjacent clearance findings** for the approximately 0.12 mm gaps. These findings are retained and documented, not suppressed. A retained **0.20 mm** netclass screen also needs explicit local assessment; the chosen PTH gaps cannot satisfy either blanket 0.15/0.20 mm target while preserving the required annulus and hole pitch.

The ring size is coupled to nearby edge routing. The first integrated route estimates were superseded after full-shape checks found two track-to-header corner/side regressions. **Final combined revision 2** keeps the same 0.88 mm lands and corrects those routes: every changed route is at least approximately **0.2030 mm from foreign header copper**, with approximately **0.2336 mm or more from the board edge**. The formerly tight VSTOR diagonal-to-square-J4.1-corner gap is now approximately **0.2144 mm**, and the long +SOLAR route-to-J3.4 gap is approximately **0.2050 mm**. These are full pad/trace geometry results, replacing the first integration's centerline-based estimates. See [revision 2 geometry and routing evidence](../routing/r2/README.md) and the [final independent combined review](../review/README.md).

The final r2 diagnostic counts are project **55**, prior uniform screen **70**, and retained-netclass screen **110**, with zero opens and the same 11 parity findings. The remaining new or changed clearance signatures concern the intentional approximately 0.12 mm **header pad pairs**, not routed tracks. Ring-only counts and measurements above remain useful reproduction evidence but are not the final integrated route audit. Neither the isolated nor combined candidate is a whole-board fabrication release.
