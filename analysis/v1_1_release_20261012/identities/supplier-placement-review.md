# U5 / U7 / U8 supplier placement review

The exported CPL centers are correct. **Fresh JLC reimport previews verify U7 at 0° and U8 at 90°, replacing their original 90° and 180° rotations.** U5 remains at 0°. The corrected orientations match the native numbered lands and independently transformed native 3D pin-1 markers. This is a supplier placement transform correction; no PCB pads, traces or native 3D model transforms require alteration.

PCB SHA-256: `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15`. Original CPL SHA-256: `cc07c7876ed4ced465ae087aa226cab75561c13cb984fba6f14970691d61688f`. [Numerical proof](supplier-placement-review.json), [required native pad/model orientation](supplier-placement-required.png). All board coordinates below use KiCad's X-right/Y-down; CPL Y is the negative of board Y. Bottom preview is north-up and horizontally mirrored.

| Part | Original CPL X, Y, rotation | Actual required orientation in supplier view | Initial preview finding |
|---|---|---|---|
| U5 TMP117AIYBGR / C2871893 | 73.148, −40.864 mm; top 0° | A1 upper-left; A2 upper-right, C1 lower-left, C2 lower-right | Matches at corner level; preserve rotation and center. |
| U7 LIS2DH12TR / C110926 | 70.548, −37.807 mm; top 90° | Pin 1 lower-left; bottom row runs 1,2,3,4 left-to-right. | Vendor white index mark initially lower-right: rotate visible model clockwise 90°. |
| U8 TLV8801DBVT / C544879 | 55.650, −36.100 mm; bottom 180° | Three leads on right, two on left. Pin 1 lower-right, 2 middle-right, 3 upper-right, 4 upper-left, 5 lower-left. | Initially three above and two below with mark upper-right: rotate visible model clockwise 90°. |

## Center and native model proof

The supplied CPL centers equal the native footprint anchors and the placement-side SMD pad bounding centers. Independently transformed native GLB dark-body bounds also center on these points: differences are 0, 0 and approximately 7×10⁻¹⁵ mm for U5, U7 and U8. The apparent offset of a supplier dot is therefore not evidence to shift a component center.

Native GLB node quaternions and translations were applied to primitive bounds. This includes each footprint's model rotation and the bottom-side transform. The actual native model's pin-1 marks are at:

| Part | Marker center, board X/Y mm | Relationship to actual land |
|---|---|---|
| U5 | 72.79175, 40.23875 | Upper-left of body; A1 land is 72.948, 40.464. |
| U7 | 69.75300, 38.57324 | Lower-left of body; pin 1 land is 69.798, 38.572. |
| U8 | 55.16635, 37.23342 | Board lower-left; bottom-view lower-right. Pin 1 land is 54.5125, 37.05. |

The marker and land need not have identical coordinates: one is on the body and the other is a solder contact. The matching corner, pin ordering and lead columns establish orientation. The UI's magenta marker is not used as an independent electrical pin map.

TI's [TMP117 YBG top view, Figure 5-2](https://www.ti.com/lit/ds/symlink/tmp117.pdf) gives A1 SDA, A2 SCL, B1 V+, B2 GND, C1 ADD0 and C2 ALERT. These match the corrected native footprint. TI's [TLV8801 DBV top view](https://www.ti.com/lit/ds/symlink/tlv8801.pdf) gives 1 OUT, 2 V−, 3 +IN, 4 −IN and 5 V+. These match the native balancer nets and the required bottom-view ordering above.

## Historical and supplier-transform limits

U5 and U7 exactly reproduce the repository's historical v1 production CPL centers and angles. This proves the export convention, **not** the supplier's final placement after any engineering/CAM adjustments. No post-adjustment v1 supplier placement file has been verified. U8 has no historical placement record. The generic bottom formula `(180 − native angle) mod 360` is consequently insufficient to qualify every supplier library's zero-angle definition.

The first correction used the supplier's clockwise-90° control. Its download button produces a preview image, not a placement CSV; that button action alone did not establish the numeric angles. The root reviewer subsequently uploaded a CSV with U7 **0°** and U8 **90°**, both at unchanged centers, and captured fresh previews. Independent inspection of those saved views verifies:

- [Reimported U7 0°](../jlc/probe-u7-0-crop.png): the vendor body index is lower-left, matching native pad 1 and the bottom row 1–4 ordering.
- [Reimported U8 90°](../jlc/probe-u8-90-crop.png): three leads are on the right and two on the left; the supplier pin-1 marker is lower-right, matching the native bottom-view pin map. The visible 3/2 lead columns independently distinguish this from the rejected horizontal original and the opposite quarter-turn.
- [U5 original 0°](../jlc/placement-u5.png): body orientation and index corner agree; preserve rotation. Its complete numbered ball mapping comes from the TI package drawing and native pad coordinates, since the supplier image cannot show the hidden balls.

These are checks against the selected JLC library models in this draft. They do not establish that arbitrary supplier libraries share the same zero-angle convention, and do not substitute for the final assembly engineering review. The exact [reimported CSV](CPL-u7-u8-reimport-probe.csv) has SHA-256 `aff66b3d61a97cfb0c83a3aa6908c3204d78a19e1219046d3e05a89e598cf7a9`; it changes only U7/U8 rotation fields. Input and image hashes are recorded in [reimport evidence](supplier-placement-reimport-evidence.json).

Original previews remain preserved: [U5](../jlc/placement-u5.png), [U7](../jlc/placement-u7.png), [U8](../jlc/placement-u8.png). The intermediate [U7 canvas](../jlc/placement-u7-corrected-canvas.png) is only the visible button-based correction; acceptance rests on the subsequent numeric CSV reimport above.

## Reproduction

`extract_placement_native.py` reads the canonical board with native KiCad and saves pin coordinates/model transforms in external scratch. Export each selected model with `kicad-cli pcb export glb --component-filter U5` (and U7/U8). `review_supplier_placement.py` applies the GLB node transforms, checks original CPL centers, compares historical input rows, and writes the JSON and diagram. It also validates the preserved numeric reimport CSV and image hashes against the recorded independent visual review. Its original CPL snapshot remains separate from any corrected export. These commands do not edit CAD or the supplier draft.
