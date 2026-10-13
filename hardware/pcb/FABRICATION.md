# v1.1 pilot fabrication and assembly intent

**Verified source and manufacturing review package; supplier approval remains pending.** This is the intended order specification, not confirmation of an order. The pilot plan is **five PCBs, three assembled**. The final fabrication ZIP is uploaded to the authorized JLC draft with five boards/three assembled, 0.4 mm ENIG, untented vias, and manual CAM/placement confirmation configured. The final BOM/CPL imports successfully in the actual three-board assembly flow: 56 references detected, 53 confirmed and selected, three inventory shortages. The available-part preview has been reviewed; shortage resolution, missing-part placement and final CAM approval remain pending. Checkout/payment is outside the authorized draft work.

## Board construction and finish

- Two copper layers, **0.40 mm finished nominal thickness**, FR4. CAD models 0.035 mm copper per face and a 0.33 mm core; confirm the fabricator's finished construction and tolerances.
- **ENIG. NO SOLDER MASK ON EITHER SIDE. NO VIA TENTING.** Expose all copper, including ground and vias. Full-board negative-polarity F.Mask/B.Mask openings are deliberate. Empty mask artwork is not an equivalent instruction; do not add local dams or tents during CAM cleanup.
- Ordinary routed outline, PTH and NPTH processes. The solar cuts are **open unplated notches**, not plated slots or castellations. No edge-plating or castellation process is selected for the 0.40 mm board.
- Preserve the existing GND/+ legends where the bare-board process permits. Final integrated native DRC retains **four silk-over-exposed-copper warnings**, with no open, parity, library, clearance or thermal finding. CAM text disposition remains pending. Do not modify copper to retain text.

Use the final source-derived copper, outline, drill, mask, paste and silk files together. Do not combine output files from separate revisions. The enabled rules use the reviewed 0.10 mm copper process floor and 0.20 mm ordinary routed-edge minimum, with explicit contact/fine-pitch exceptions and nominal annulus requirements. Those CAD checks are not a substitute for final CAM acceptance of the specified bare finish.

## Stencil and automated assembly

Preserve selective **F.Paste/B.Paste** data. No solder mask does not mean paste over the exposed board. U7's twelve apertures already have **81% of their copper-land area** (90% linear size); avoid a second global reduction. The proposed stencil reference is **100 µm**, within ST's 90–150 µm recommendation; confirm the assembler's final stencil, paste and double-sided process. Inspect actual aperture geometry, not only a percentage setting.

The BOM uses explicit `Manufacturer_Part_Number` and `Supplier Part` fields, reconciled against the actual flown JLC selections and approved changes. U5 is **TMP117AIYBGR C2871893**, not the earlier N-grade label. D1/D3 are **PESD5V0U1BB C5272735**. Preserve the reviewed pin-1 orientations during final supplier CAM and check missing ICs when available. U8 is on **B.Cu at (55.65, 36.10) mm**, native rotation 0°. Its supplier CPL rotation is **90°**, established by native numbered lands, supplier preview and reimport; the bottom view has three leads at right, two at left and pin 1 at lower right.

The power selection passes **final integrated native and connectivity verification**: R1 7.50 MΩ (`FRC0402F7504TS C3013187`), U8 `TLV8801DBVT C544879`, R24/R25 `FRC0402F4754TS C2998153`, R26 `0402WGF220JTCE C25092`, and C22 `CL05B104KO5NNNC C1525`. Final BOM inclusion must follow the final approved schematic and export manifest. D3.1/J4.1 have local 0.25 mm thermal gaps/bridges; preserve their supplied copper rather than replacing the footprints during CAM.

The manufacturing generator excludes hand-fitted and mechanical items from automated BOM/CPL. Its baseline convention reproduces the repository's v1 production **input** CPL and uses SMD pad bounds rather than text/model bounds. That historical input does not establish the supplier's final post-CAM rotations. Actual JLC preview and reimport checks now establish **U1 90°, U4 270°, U7 0°, U8 90°**, recorded in the [supplier rotation profile](../../analysis/v1_1_release_20261012/jlc/supplier-rotation-profile.json). U3 remains 180° and U5 remains 0°. No center, side, pad, or trace changes are needed. U4's black circle is its pressure port; use the separate pin-1 indicator and numbered package drawing. The partial preview contains all 53 available references; R4/U2/U6 remain missing. Complete placement confirmation is pending those parts and final supplier CAM.

## Manual assembly after reflow and cleaning

**C5 supercapacitor:** retain the flat `DMF4B5R5G105M3DTA0` assembly. It is not a normal reflow part. Follow the CAP-XX secondary soldering process and install it after cleaning. Do not reflow the capacitor with the rest of the board. Preserve pad 1 positive / pad 2 negative / pad 3 physical midpoint. The frozen balanced circuit assigns pad 3 to `SC_MID`; do not swap the outer polarity or treat the center as a ground lead. Confirm the final exported circuit and measure each cell before flight.

**J1/J2 solar panels:** each 1.0 mm-wide × 2.0 mm-deep notch is unplated. Seat the prepared negative terminal against the straight upper bank, then wet the GND land on both faces; the target model has approximately 1.3 mm straight-bank overlap. Positive connections use separate lower 0.70 mm holes. The illustration uses 0.50 mm solid wire with short formed ends and insulation on the return. Check real terminal thickness/exposed foil before soldering. Do not infer mechanical strength or bend limits from the photo-scaled model.

**J3/J4 programming wires:** 1.00 mm pitch, 0.50 mm holes; solder temporary wires on the larger 1.20 × 0.88 mm rear lands. Front lands remain 0.88 mm. Preserve pad-1 orientation. These contacts are excluded from automated placement; confirm actual wire fit and avoid excess solder bridging the approximately 0.12 mm adjacent-land gap.

**AE1/AE2 antennas:** hand-form straight enameled copper wire and strip enamel only where soldered. The [published starting cuts](https://stratolink.org/docs/hardware#antennas-and-suspension), measured from the feed, are 82 mm for 915 MHz LoRa, 86 mm for 868 MHz, 83 mm compromise, and 48 mm for GNSS L1. The CAD reference is 82/48 mm. Record the actual wire diameter, cut and soldered exit shape, then evaluate the completed RF/GNSS assembly. These are not orderable spring/chip antennas.

**H1/H2 suspension:** 2.00 mm plated holes with 3.20 mm GND rings. Thread the actual thin stretchy line through both holes to form the triangular bridle. Check rim wear and corner loading on the pilot. J20 remains an unsoldered Tag-Connect interface.

## Release record and pilot checks

The [README release record](README.md#rules-and-release-state) pins all four verified source hashes. Native checks show zero opens/parity/library mismatches and four retained silk warnings. Filtered ERC is zero with three narrowly documented exclusions; raw two-error/one-warning evidence remains available. The canonical-source export has 56 assembly references, 30 part groups and 10 exclusions; all 12 U7 paste apertures retain 81% area. The [final package manifest](../gerbers/v1.1-pilot/manifest.json) pins the canonical source and all Gerber/drill/BOM/CPL/ZIP files. JLC allocation/placement/CAM remains **PENDING**. Order status: **NOT PLACED**.

| Package file | SHA-256 |
|---|---|
| [BOM-stratolink.csv](../gerbers/v1.1-pilot/BOM-stratolink.csv) | `a8316e5907e24c0a336a23464fdd46f2c4492f055caccef7d20f6f6b0d2bad38` |
| [CPL-stratolink.csv](../gerbers/v1.1-pilot/CPL-stratolink.csv) | `eb8ef43bb3b1a6ee0b1efc3f3c1280f519686b6ba1fda44e61ace8cc6c4d1069` |
| [fabrication-review.zip](../gerbers/v1.1-pilot/fabrication-review.zip) | `a40250993aee05254827a5090b7b569212d70bfcd8844bfa68adf0870c42a086` |


The actual October 13 assembly import reports three exact-part shortages:

| Reference / part | Required including displayed allowance | Available | Shortage |
|---|---:|---:|---:|
| R4 / C2766827 | 20 | 0 | 20 |
| U2 / C18548052 | 3 | 1 | 2 |
| U6 / C492374 | 3 | 0 | 3 |

R6 / C423131 is confirmed with its 20-piece feeder quantity available. The public BOM tool's earlier header/quantity defects do not appear in the actual assembly flow. Resolve the three shortages without silently substituting parts; successful import does not reserve inventory or approve placement. [Actual assembly import evidence](../../analysis/v1_1_release_20261012/jlc/assembly-bom-match.txt).

Before the larger batch, verify the corrected TMP117 directly, quiet omitted-microphone pins, sensor/GNSS operation, solar joint/bridle strength and RF behavior. For the new power circuit, measure charge plateau, individual cells, balancing current/stability at startup and cold conditions, and supply sag during radio/GNSS load. **Panel cold Voc/current and the harvester input-voltage/input-power limits remain unresolved physical bounds.** A clean layout check cannot qualify those operating conditions.

See [README.md](README.md), [TODO.md](TODO.md), the [power review](../../analysis/v1_1_release_20261012/power/README.md) and the [manufacturing export method](../../analysis/v1_1_release_20261012/manufacturing/README.md).
