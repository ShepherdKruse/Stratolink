# v1.1 AS7331 pilot — current release status

Canonical project: `hardware/pcb`, branch `alpha/hardware-v1.1`. Final status: **promoted to the canonical hardware folder / native and independent electrical/geometry checks passed; factory CAM and physical qualification pending**. Use the [canonical README](../../hardware/pcb/README.md) for source hashes and the [fabrication record](../../hardware/pcb/FABRICATION.md) for exact assembly intent. The user authorized a reviewed JLC cart draft for **five PCBs / three assembled**; checkout/payment is not authorized.

The UV decision is settled: **AS7331-AQFM C20482877** in the complete native design, with **U6 omitted only** for the first pilot. **C14/C23 100 nF and R27 MCU0805MD3304BP500, 3.3 MΩ ±0.1% ±25 ppm/K, remain fitted.** The pilot BOM/CPL and stencil carry that explicit population; full-design paste is retained separately. Circuit, sourcing, primary-source limits and review evidence are collected in [the AS7331 record](as7331/README.md).

## Current work and evidence

| Item | Status / record |
|---|---|
| Earlier v1.1 changes | TMP117 correction, microphone removal, solar notches/models, suspension rings, enlarged PTH programming lands, green mask/no silkscreen, ground/edge cleanup, U7 paste/routing, exact identities, charge ceiling and balancing circuit retained. [Manual review](manual-review-changes.md). |
| UV placement and local routing | **U6 (74.25, 37.10 mm), C14 (74.30, 34.50 mm), front side**; scope **local SDA/SCL, PB5, VSTOR and GND rerouting; C21 shifts 0.90 mm left to (69.362, 34.647 mm), C6 stays fixed; C23 at (75.20, 39.80 mm), R27 at (71.90, 34.08 mm); 0.15 mm local I²C/supply routing, short 0.125 mm GND necks; PB5/VSTOR retain 0.25 mm; original copper branding retained, solar +/- legends in exposed copper**. Retained component moves are U6/C14 and the documented C21 bypass adjustment. |
| Final native and independent review | DRC **0 violations, 0 open connections, 0 schematic mismatches**; ERC **0 unexcluded errors or warnings; two documented exclusions retained**. Only U5 ALERT / U7 SA0 exclusions remain; AS7331 READY is NC. Evidence **[independent review](../../analysis/v1_1_release_20261012/as7331/review/README.md)**. |
| Manufacturing package | **58 full / 57 pilot references**, **30 distinct pilot part groups**, **11 exclusions**. [Manifest](../../hardware/gerbers/v1.1-pilot/manifest.json): **166 inputs / 37 outputs**. |
| Population and stencil checks | Identity-bound U6-only omission, 16 U6 paste apertures suppressed, C14/C23/R27 retained, all other rows/apertures and source/output/ZIP hashes checked. [Verification method](as7331/manufacturing/README.md). Final result **passed: 57/58 references, U6-only omission, 16 apertures removed, 166 source and 37 output hashes plus all 12 ZIP members verified**. |
| Pilot firmware | **`stratolink_v1_1_uv_dnp`** builds; no optical transactions or waits, unavailable UV/lux, quiet microphone pins. Earlier v1.1 firmware.bin remains byte-identical. [Evidence](as7331/firmware/README.md). A populated AS7331 driver remains unimplemented. |
| Supplier/cart | **Saved and verified:** [JLC cart](https://cart.jlcpcb.com/shopcart/cart), item **fabrication-review_Y24**, PCB **Y24-2680969A**, PCBA **SMT026101364685-2680969A**. All 57 exact MPN/LCSC selections passed independent review; top/bottom placements were reviewed with U6 absent and no browser rotation changes. Five PCBs / three assembled, Standard Both Sides; **US$332.47** before shipping, tax and advanced-remark review changes. [Supplier evidence](as7331/jlc/README.md). |
| Factory confirmation | Production-file and parts-placement confirmation enabled; manual approval required, automatic changes disabled. Green/no-silk, rail/tab layout and final CAM approval remain pending. Cart rail envelope **71.36 × 71.30 mm**; actual board **23.36 × 57.30 mm**. No checkout/payment. |
| Unrelated working changes | Original scope baseline `baseline.json` protects 100 unrelated tracked changes. Final preservation evidence **[promotion and preservation record](../../analysis/v1_1_release_20261012/as7331/promotion.json)**. |

The old Y22 fifteen-board cart item remains unchanged; its out-of-stock warning is scoped to Y22, not the new Y24 pilot. Saved price comprises US$70.63 PCB and US$261.84 assembly. Saved construction is green 0.40 mm FR4, 1 oz copper and ENIG with 1 µin gold.

The retained supplier CPL profile is **U1 90°, U2 90°, U4 270°, U7 0°, U8 90°; U3 180°, U5 0°**. These are supplier conventions, not native footprint moves. U6 is not in the pilot CPL; its future exact model needs a separate placement review. [Profile and evidence](jlc/supplier-rotation-profile.json).

## Limits still requiring physical work

- Measure panel cold Voc/I–V and actual BQ25570 input voltage/power. Historical telemetry reaching 5.538 V is uncalibrated ADC evidence, not proof of actual pin stress or a resolved input limit.
- Qualify both capacitor cell voltages, charge plateau, midpoint startup/stability, cold ESR/leakage and radio/GNSS load transients. Keep the flat capacitor out of board reflow.
- Inspect sensor operation, unavailable-data reporting, night current, sunrise recovery, solar joints, suspension wear and installed RF/GNSS behavior using the [pilot acceptance procedure](pilot-acceptance.md).
- Later AS7331 population needs firmware, controlled-angle optics, solar VIS/NIR rejection and independent calibration. Separate UV bands enable an experimental column above the balloon; they do not alone establish ozone accuracy. U6-DNP pilots produce no UV measurements.

Earlier detailed reports in `sourcing_followup/`, `jlc/`, `power/`, `identities/` and `erc/` remain historical evidence. Their previous UV indecision, LTR390 shortage, three-exclusion ERC count, source hashes, partial prices and supplier selections do not identify the final AS7331 package. Only the final canonical hashes, manifest and current supplier evidence do.
