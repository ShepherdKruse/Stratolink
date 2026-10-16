# Supplier orientation checklist, 16 October 2026

Candidate reference only. Fresh JLC screenshots have not yet been reviewed.

PCB: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`

CPL: `bc35d68dcf8d80f05098ff822155f5f8e560cac0e1e6f120e70e3f256fac7adb`

View convention: suspension holes at the top. Read each component from its mounted face. A bottom view mirrors native X, while north remains up. Native KiCad coordinates below use X right/Y down as seen from the top. Compare numbered pads and the package index, not text direction or a raw rotation number.

| Part | Native / draft CPL | Required appearance in north-up mounted-face preview | Native pin-1 location, mm |
|---|---|---|---|
| **U1 BQ25570** | **Bottom 180° / 270°** | **Index upper-left in bottom view.** Twenty perimeter leads and center exposed pad. New 180° rotation from previous board; old lower-right screenshot is stale. | 1 = (68.841, 36.815), GND |
| U2 RAK3172 | Top 180° / 90° | Index lower-left; the twelve-pad edge is along the bottom. Shield/U.FL body stays within its perimeter lands. | 1 = (59.215, 79.605) |
| U3 MAX-M10S | Top 180° / 180° | Index lower-right. Module body and lead rows align with lands. | 1 = (70.980, 52.800), GND |
| U4 MS5611 | Top 0° / 270° | Separate package index upper-left; 3 × 5 mm body vertical. The large dark pressure port is not the pin-1 marker. | 1 = (69.823, 56.933), +3.3 V |
| **U5 TMP117** | **Top 180° / 180°** | **A1 index lower-right.** Old upper-left screenshot is stale. Three ball rows run vertically; 2 columns horizontally. | A1 = (64.700, 41.830), SDA |
| U7 LIS2DH12 | Top 90° / 0° | Index lower-left, consistent with pin 1 on lower row. | 1 = (69.798, 38.572), SCL |
| **U8 TLV8801** | **Top 180° / 180° provisional** | **Front side, three leads right, two left; pin 1 lower-right.** Pin 3 upper-right; pin 4 upper-left; pin 5 lower-left. Face change makes prior bottom convention unusable. | 1 = (57.710, 50.170), SC_BAL_OUT |

U8 must connect pin 2 at right-center to GND, pin 3 upper-right to SC_HALF_REF, pin 4 upper-left to SC_BAL_OUT and pin 5 lower-left to VBAT. U5's remaining ball map is A2 lower-left SCL, B1 right-center +3.3 V, B2 left-center GND, C1 upper-right GND, C2 upper-left GND.

U2's CPL center is (64.950, -72.205), whereas its native footprint origin is (72.715, 64.660). This is the existing intentional body-center correction; compare lands/body, not those unlike origins directly.

## Diodes and other parts

- **D1 and D3 are bidirectional PESD5V0U1BB**, not unidirectional polarity-sensitive rectifiers. Preserve their footprint alignment. D1 is horizontal at CPL 180°, pad 1/GND to the right, antenna pad 2 to the left in top view. D3 is vertical at CPL 90°, pad 1/GND below, antenna pad 2 above. The retained part identity means a 180° reversal is not an anode/cathode failure, but a 90° misalignment is unacceptable.
- Fitted C1–C23 references in the BOM are MLCCs and nonpolar. Resistors and FB1 are nonpolar; rectangular bodies must match their two lands. L1/L2 are nonpolar inductors; check body/land alignment, with both on the bottom. Their draft CPL angles are 180° and 0° respectively.
- **C5 is polarized and hand-fitted, absent from automated placement.** In north-up rear view its three terminals read left-to-right **negative/GND (pad 2), midpoint/SC_MID (pad 3), positive/VBAT (pad 1)**. Midpoint is not GND. This is a manual assembly check, not a JLC model-orientation requirement.

## Population and saved evidence

1. Confirm **57 placed references: 41 top, 16 bottom**, with exact BOM MPN/LCSC matches. U1 is the only bottom-side IC; U8 is on the top.
2. **U6 is absent**, while **C14, C23 and R27 remain present**. Antennas, C5, solar attachments, programming contacts and suspension hardware stay outside automated placement.
3. Save a north-up overall image of each face, plus sufficiently zoomed U1, U5 and U8 images showing the supplier index and lead/land mapping. Capture U2/U3/U4/U7 indices and the two diode body alignments as well.
4. Supplier angles are provisional until those images agree. Record any correction in the profile and regenerate/reimport CPL so saved files match the preview. Do not infer a required angle from the KiCad angle alone.

Inputs: current PCB, package BOM/CPL and `analysis/v1_1_engineer_review_20261015/mechanics/models-pads.json`. The accompanying JSON records hashes, all 57 CPL rows and critical native pad positions. Diode identity follows `analysis/v1_1_release_20261012/identities/README.md`. No CAD changes were made.
