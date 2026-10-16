# AS7331 population on the three Y25 pilots

**The frozen Y25 board already contains the complete AS7331 circuit. Populating U6 does not require a footprint or routing change on that reviewed design.** The immediate changes are a full-population assembly package, a qualified stencil/process and a fresh supplier U6 orientation check. Firmware work can proceed alongside procurement, but populated-sensor bring-up is needed before flight.

This read-only review uses frozen PCB `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`. The [Y25 package manifest](../../hardware/gerbers/v1.1-pilot-supplier-20261016/manifest.json) records its frozen inputs. Native U6 pose, all sixteen pad nets and geometry were rechecked read-only against that source; U6 itself is unchanged in the current dirty file.

## Minimum assembly changes

1. Add the exact AS7331 orderable to BOM/CPL and remove the U6-only population omission in a **new** export. Result: **58 automatic-assembly references, 42 top / 16 bottom, 31 distinct part groups**, retaining C14, C23 and R27. Keep the confirmed supplier U8 angle at 90°. Do not overwrite the frozen DNP package.
2. Restore **all 16 U6 front-paste apertures** using the complete-design paste. The current pilot ZIP deliberately has none. Verify that only this population/paste delta changes; all other paste, copper, mask, outline and drills stay matched to the reviewed source.
3. Obtain a fresh exact-part supplier preview. U6 is at **(74.25, 37.49) mm, F.Cu, native 180°**. The required top-view pin-1 corner is **lower-right**, with pad 1/GND at **(75.000, 39.065) mm**. The existing full-design CPL calculation is 180°, but this has never been qualified against the supplier AS7331 model. Preserve the native package and adjust only the supplier convention if preview requires it.
4. Have the assembler qualify the existing derived land/stencil pattern: **0.35 mm square copper, 0.30 mm square paste, 0.50 mm row pitch**, with no central exposed-pad paste. A **100 µm stencil** gives an aperture-area/wall-area ratio of 0.75; 120 µm gives 0.625. These are engineering calculations, not an ams recommended land pattern. Avoid an additional blanket reduction. Preserve tenting over nearby/underbody vias and check finished mask integrity.

The sixteen-pin map matches the source requirements: VDDA/VDDD on 3.3 V; separate C14/C23 100 nF bypasses; 3.3 MΩ precision R27 from REXT to ground; A0/A1 grounded for address **0x74**; SYN grounded for command-mode use; READY unconnected. R27's selected ±0.1%, ±25 ppm/K part exceeds the sensor's ±1%, ≤50 ppm/K reference specification. Keep the high-impedance reference area clean.

## Exact package and handling

**AQFM versus AQFT:** manufacturer DS001047 v4-00, printed p6, lists both as **OLGA16, AS7331 marking, tape and reel**. The documented distinction is **1,000 pieces/reel for AQFM and 5,000 for AQFT**. The same electrical and package specifications apply; no alternate die or footprint is listed. Keep the exact purchased suffix and supplier identity in the assembly record. This is not evidence of either supplier SKU's stock, minimum purchase or accepted cut-tape format.

Figure 59 shows a **2.60 × 3.65 × 1.09 mm** nominal optical LGA with sixteen perimeter terminals and a centered optical aperture. Its contact-dimension drawing is a bottom view; the top-view pin-1 dot is the orientation reference. Figures 60/61 were visually read, but key carrier variables such as width W and pocket pitch P1 are not numerically specified there. Do not invent a feeder width or assume the smaller reel quantity means a different package. Supplier tape length, leader, spares/attrition and consignment acceptance need confirmation from the actual assembly route.

Manufacturer handling requirements, printed pp67–69:

- **MSL 3:** 168 hours after opening, at **<30 °C and <60% RH**. Preserve moisture-barrier packaging, desiccant and humidity-history information for externally sourced/cut tape.
- Unopened shelf life: **24 months**, stored **<40 °C / <90% RH**. An exceeded limit or unacceptable humidity indicator requires rebaking. The specified rebake is **50 °C for 12 hours**; do not substitute a generic high-temperature bake without approval.
- Reflow profile: average preheat **2.5 °C/s**, soak **2–3 minutes**, at most **60 s above 217 °C**, **50 s above 230 °C**, **10 s above peak minus 10 °C**, peak **260 °C**, cooling rate limited to the stated **5 °C/s** magnitude. The assembler must accommodate this in the double-sided process. A maximum pass count and optical-safe pickup-nozzle specification were not verified here.
- Use the manufacturer's neutral cleaning guidance, including IPA; avoid acidic or alkaline cleaners. Keep the optical aperture free of flux residue, paste, glue, tape and coatings. ESD-controlled handling is appropriate to the stated **750 V HBM / 500 V CDM** ratings.

## Firmware and measurement readiness

Current `stratolink_v1_1_uv_dnp` deliberately makes **no optical transactions**. The legacy target talks to LTR390; neither is an AS7331 measurement driver. A populated build needs identity/ACK checks at 0x74, bounded conversions and fault recovery, raw UVA/UVB/UVC plus exposure/gain/status telemetry, saturation rejection and measured low-power behavior after initialization, conversion and shared-bus recovery.

The primary datasheet explicitly says that a real power-on reset or software reset starts AS7331 in **Power-Down**. Do not claim that merely fitting it forces a continuous 2 mA load. However, DNP firmware neither verifies nor restores that state after all operating/recovery conditions, so it is not a qualified populated-sensor flight image. Manufacturer table limits are **2 mA active**, **970 µA standby**, **1 µA power-down** under its stated conditions. Confirm sleep current on the actual assembled board.

Assembly does not establish an ozone retrieval. Optical angle control, solar visible/IR rejection, calibration and the actual −40…85 °C device temperature envelope remain later measurement gates.

## Source caution

The live CAD currently hashes `01bc0ba752b88678f9ee01fbc2c173c7eaedded96f983bcd0f6df5ea971c95e3`, differing from the frozen Y25 file. U6 itself has identical pose, pad geometry, nets and fields. The live diff includes five fabrication-text hide flags **and a deleted VSTOR rear trace segment**. Preserve that dirty state; resolve the chosen source before exporting a populated revision. This note does not approve the live deletion.

Primary documents read: [ams DS001047 v4-00, 2023-03-24](../v1_1_release_20261012/as7331/review/as7331-datasheet-v4-00.pdf), printed pp6,9–10,15,23–24,64–69; package/reel/reflow/storage pages were rendered and inspected. The PDF SHA-256 is `60c13168a4012c1642277b8d8f9557e6f835c3b9efbfd7cc086be25c5a4c670a`. [Design guidelines PD001048 v2-00](../v1_1_release_20261012/as7331/review/design-guidelines.pdf), incidence guidance and §7.7, support the optical limits. [Firmware population record](../v1_1_release_20261012/as7331/firmware/README.md), [current target configuration](../../firmware/platformio.ini) and [driver source](../../firmware/src/sensor_ltr390.cpp) establish the remaining firmware work.

No CAD, cart, firmware or frozen evidence files were changed. Current stock, purchasing routes and consignment fees are covered separately by the procurement review.
