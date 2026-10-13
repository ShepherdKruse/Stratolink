# v1.1 AS7331 pilot — current release status

**DRAFT — final AS7331 promotion and supplier completion are not yet claimed.** Canonical project: `hardware/pcb`, branch `alpha/hardware-v1.1`. Final status: **{{FINAL_PROMOTION_STATUS}} / {{FINAL_REVIEW_STATUS}}**. Use the [canonical README](../../hardware/pcb/README.md) for source hashes and the [fabrication record](../../hardware/pcb/FABRICATION.md) for exact assembly intent. The user authorized a reviewed JLC cart draft for **five PCBs / three assembled**; checkout/payment is not authorized.

The UV decision is settled: **AS7331-AQFM C20482877** in the complete native design, with **U6 omitted only** for the first pilot. **C14/C23 100 nF and R27 MCU0805MD3304BP500, 3.3 MΩ ±0.1% ±25 ppm/K, remain fitted.** The pilot BOM/CPL and stencil carry that explicit population; full-design paste is retained separately. Circuit, sourcing, primary-source limits and review evidence are collected in [the AS7331 record](as7331/README.md).

## Current work and evidence

| Item | Status / record |
|---|---|
| Earlier v1.1 changes | TMP117 correction, microphone removal, solar notches/models, suspension rings, enlarged PTH programming lands, green mask/no silkscreen, ground/edge cleanup, U7 paste/routing, exact identities, charge ceiling and balancing circuit retained. [Manual review](manual-review-changes.md). |
| UV placement and local routing | **{{FINAL_UV_LOCATION}}**; scope **{{FINAL_UV_ROUTING_AND_LABEL_SCOPE}}**. Retained component moves are U6/C14 and the documented C21 bypass adjustment. |
| Final native and independent review | DRC **{{FINAL_DRC_RESULT}}**; ERC **{{FINAL_ERC_RESULT}}**. Only U5 ALERT / U7 SA0 exclusions remain; AS7331 READY is NC. Evidence **{{FINAL_INDEPENDENT_REVIEW_LINK}}**. |
| Manufacturing package | **{{FINAL_FULL_ASSEMBLY_COUNT}} full / {{FINAL_PILOT_ASSEMBLY_COUNT}} pilot references**, **{{FINAL_PILOT_PART_GROUPS}} pilot groups**, **{{FINAL_EXCLUSION_COUNT}} exclusions**. [Manifest](../../hardware/gerbers/v1.1-pilot/manifest.json): **{{FINAL_SOURCE_FILE_COUNT}} inputs / {{FINAL_OUTPUT_FILE_COUNT}} outputs**. |
| Population and stencil checks | Identity-bound U6-only omission, 16 U6 paste apertures suppressed, C14/C23/R27 retained, all other rows/apertures and source/output/ZIP hashes checked. [Verification method](as7331/manufacturing/README.md). Final result **{{FINAL_POPULATION_VERIFICATION_STATUS}}**. |
| Pilot firmware | **`stratolink_v1_1_uv_dnp`** builds; no optical transactions or waits, unavailable UV/lux, quiet microphone pins. Earlier v1.1 firmware.bin remains byte-identical. [Evidence](as7331/firmware/README.md). A populated AS7331 driver remains unimplemented. |
| Supplier/cart | Selection and placement **{{FINAL_JLC_SELECTION_STATUS}} / {{FINAL_PLACEMENT_REVIEW_STATUS}}**; green-mask/no-silkscreen/rails/CAM **{{FINAL_CAM_STATUS}}**; cart **{{FINAL_CART_STATUS}}**, **{{FINAL_CART_LINK}}**. Uploaded package proof **{{FINAL_JLC_EVIDENCE_LINK}}**. |
| Unrelated working changes | Original scope baseline `baseline.json` protects 100 unrelated tracked changes. Final preservation evidence **{{FINAL_SCOPE_AUDIT_LINK}}**. |

The retained supplier CPL profile is **U1 90°, U2 90°, U4 270°, U7 0°, U8 90°; U3 180°, U5 0°**. These are supplier conventions, not native footprint moves. U6 is not in the pilot CPL; its future exact model needs a separate placement review. [Profile and evidence](jlc/supplier-rotation-profile.json).

## Limits still requiring physical work

- Measure panel cold Voc/I–V and actual BQ25570 input voltage/power. Historical telemetry reaching 5.538 V is uncalibrated ADC evidence, not proof of actual pin stress or a resolved input limit.
- Qualify both capacitor cell voltages, charge plateau, midpoint startup/stability, cold ESR/leakage and radio/GNSS load transients. Keep the flat capacitor out of board reflow.
- Inspect sensor operation, unavailable-data reporting, night current, sunrise recovery, solar joints, suspension wear and installed RF/GNSS behavior using the [pilot acceptance procedure](pilot-acceptance.md).
- Later AS7331 population needs firmware, controlled-angle optics, solar VIS/NIR rejection and independent calibration. Separate UV bands enable an experimental column above the balloon; they do not alone establish ozone accuracy. U6-DNP pilots produce no UV measurements.

Earlier detailed reports in `sourcing_followup/`, `jlc/`, `power/`, `identities/` and `erc/` remain historical evidence. Their previous UV indecision, LTR390 shortage, three-exclusion ERC count, source hashes, partial prices and supplier selections do not identify the final AS7331 package. Only the final canonical hashes, manifest and current supplier evidence do.
