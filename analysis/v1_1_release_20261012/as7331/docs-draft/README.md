# Stratolink hardware — v1.1 pilot

**DRAFT — AS7331 update prepared for root review; not a promotion or manufacturing-release claim.** Final canonical status: **{{FINAL_PROMOTION_STATUS}}**. Final native/independent review: **{{FINAL_REVIEW_STATUS}}**. JLC cart status: **{{FINAL_CART_STATUS}}**. Payment is not authorized.

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. The canonical project lives in `hardware/pcb` on `alpha/hardware-v1.1`; Git retains the flown v1. Keep `lib/`, `3d/`, `sym-lib-table` and `fp-lib-table` together. Board-specific footprints preserve reviewed local geometry; avoid blanket stock-library replacement.

The approved pilot design keeps the **0.40 mm, two-layer board, ENIG, green solder mask on both faces, no silkscreen, and tented ordinary vias**, one radio, the existing GNSS/pressure/IMU parts and the flat rear capacitor. Selective mask openings expose soldering lands; stencil paste is separate. The plan is **five fabricated boards, three assembled**, followed by physical qualification before a larger batch.

## Approved UV circuit and pilot population

U6 changes from LTR390 to **ams AS7331-AQFM, C20482877**, with separate UVA/UVB/UVC channels, 3.3 V supplies and I²C address **0x74**. U6 and its existing C14 bypass move to **{{FINAL_UV_LOCATION}}**. New **C23, 100 nF CL05B104KO5NNNC C1525**, bypasses the second supply; new **R27, Vishay MCU0805MD3304BP500 C4313228**, provides the 3.3 MΩ, ±0.1%, ±25 ppm/K reference. C14 uses the same 100 nF part. READY stays unconnected; SYN and the address inputs are grounded for polled command-mode operation. Final local routing and copper-label scope: **{{FINAL_UV_ROUTING_AND_LABEL_SCOPE}}**. Any additional retained-component moves are explicitly recorded in the final routing scope.

The native design includes the **complete populated circuit**. The initial assembly variant deliberately **omits U6 only**, retaining **C14, C23 and R27**. Its BOM/CPL omit U6, and its pilot stencil omits exactly the 16 U6 apertures. Full-design paste remains in the package for a later separately reviewed population. Do not use the DNP stencil for that later build. See the [integration record](../../analysis/v1_1_release_20261012/as7331/README.md), [exact sourcing](../../analysis/v1_1_release_20261012/as7331/sourcing/README.md) and [population/stencil checks](../../analysis/v1_1_release_20261012/as7331/manufacturing/README.md).

Use **`platformio run -e stratolink_v1_1_uv_dnp`** from `firmware/` for these U6-absent pilots. It leaves microphone pins PB3/PB4 quiet, makes no optical I²C requests and reports UV/lux unavailable. The earlier `stratolink_v1_1` target expects an LTR390 board; a **populated AS7331 has no supported flight target yet** and requires a dedicated driver, verified power-down and raw multiband telemetry. Do not fit AS7331 and continue using DNP firmware. Existing flown-v1 firmware behavior is preserved. [Firmware scope and verification](../../analysis/v1_1_release_20261012/as7331/firmware/README.md).

AS7331 enables an experimental **ozone column above the balloon**, not a calibrated concentration by itself. It has no visible-light ALS channel. Its −40…85 °C limit requires actual die-temperature verification; sensor mass is not specified in the inspected primary datasheet. At 3.3 V, active current is 1.42 mA typical / 2 mA maximum under the stated table conditions. One second per minute followed by maximum specified power-down is about **113 µW sensor-only average**; this is an illustrative duty cycle, not a selected exposure. The manufacturer recommends incidence within ±10° and warns that solar visible/IR leakage can overwhelm weak UV signals. An unobstructed chip does not provide angle control or spectral blocking. Collector/filter design, calibration, raw-data processing and low-pressure/thermal qualification remain necessary; U6-absent pilots produce no UV or ozone data. [Primary-source review](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).

## Other v1.1 changes

| Area | Pilot configuration |
|---|---|
| Precision temperature | Corrected U5 **TMP117AIYBGR C2871893** ball map and local routing; address 0x48. The earlier N-grade label was inaccurate. |
| Microphone | MK1/R20/C13, dedicated routing and acoustic opening removed; PB3/PB4 unused. |
| Solar mounting | Two **1.0 × 2.0 mm open unplated notches**, upper-bank GND lands on both faces, and separate lower **0.70 mm positive wire holes**. Panels stay parallel. |
| Suspension | **2.0 mm plated holes / 3.2 mm GND rings**, at the original centers, for the triangular string bridle. |
| Programming access | J3/J4 remain ordinary **PTH contacts**, not edge connectors or castellations: 1 mm pitch, 0.50 mm holes, 0.88 mm front lands, **1.20 × 0.88 mm rear lands** offset 0.12 mm inward. |
| Antennas | Straight enameled copper wire: reference cuts **82 mm for 915 MHz / 48 mm for GNSS L1**, measured from the feed. Documented LoRa alternatives are 86 mm at 868 MHz and 83 mm compromise. |
| U7 assembly | Existing twelve copper lands retained, **81% paste area**, explicit ground returns and clear central underside routing. |
| Ground and small routing | Zones, thermals, near-edge routes and wire-antenna envelopes reconciled; tiny duplicate VSTOR segment removed. |
| Identities and sourcing | Exact shipped identities and frozen local libraries; R4 **RC0402FR-073M65L C477700**, U2 **RAK3172-8-SM-NI C5452091**, D1/D3 **PESD5V0U1BB C5272735**. R4/U2 substitutions retain existing lands and nets. |

U5's map is **A1 SDA, A2 SCL, B1 +3.3 V, B2 GND, C1 GND, C2 unused ALERT grounded** as TI permits. The AI grade is specified to ±0.2 °C over −40…100 °C and ±0.25 °C over −55…125 °C under its stated conditions; board sunlight and conduction add ambient-air error. [Identity review](../../analysis/v1_1_release_20261012/identities/README.md).

The [solar 3D models](3d/solar/README.md) show photo-scaled 94 × 75 mm panels, straight roots, curved film and formed positive wires. Terminal thickness, prepared wettable area, wire dimensions and joint strength still need measurement. The model is an assembly guide, not a measured load rating.

## Power and storage

R1 is **7.50 MΩ FRC0402F7504TS C3013187**, with R2 at 4.22 MΩ, giving a nominal **5.041 V** charge ceiling. The flat C5 remains: **pad 1 positive, pad 2 negative, pad 3 SC_MID**. The upper-left rear balancing circuit uses **U8 TLV8801, R24/R25 4.75 MΩ, R26 22 Ω, C22 100 nF**. Feedback joins the amplifier output to its inverting input **before R26**; R26 connects to the capacitor midpoint. The circuit runs from the capacitor stack. The required VSTOR ADC branch is rerouted. D3.1/J4.1 retain local 0.25 mm thermal gap/bridge widths and a two-spoke minimum.

The [power review](../../analysis/v1_1_release_20261012/power/README.md) records tolerance assumptions and startup/stability limits. Charge plateau, individual cell voltages, cold behavior, leakage and balancing stability require measurement. **Panel cold Voc/current and BQ25570 input-voltage/input-power bounds remain unresolved.** Neither the panel label nor existing telemetry establishes those operating limits. C5 is hand-fitted after reflow and cleaning, following its secondary soldering process.

## Rules, evidence and supplier state

Rules use a **0.10 mm copper process floor, 0.15 mm general clearance target and 0.20 mm ordinary routed-edge minimum**, with named fine-pitch/contact constraints. Clearance, edge, annular and solder-mask checks are enabled. The mask screen targets a 0.10 mm minimum web and 0.09 mm opening-to-foreign-copper clearance; supplied apertures require supplier confirmation. The obsolete LTR390/U7 corridor rule is removed with the old U6 geometry. The intended ERC exclusions are now **two**: U5 grounded ALERT and U7 SA0; old U6 grounded INT is gone and AS7331 READY is explicitly NC. All native silkscreen artwork is removed. Solar polarity symbols are copper features with matching mask openings.

Final native DRC: **{{FINAL_DRC_RESULT}}**. Final ERC, including raw findings and the two narrow exclusions: **{{FINAL_ERC_RESULT}}**. Independent connectivity/geometry evidence: **{{FINAL_INDEPENDENT_REVIEW_LINK}}**. These placeholders must be completed from the final promoted files, not copied from an earlier revision.

| Canonical file | Final SHA-256 |
|---|---|
| PCB | `{{FINAL_PCB_SHA256}}` |
| Schematic | `{{FINAL_SCHEMATIC_SHA256}}` |
| Project | `{{FINAL_PROJECT_SHA256}}` |
| Rules | `{{FINAL_RULES_SHA256}}` |

The [manufacturing package](../gerbers/v1.1-pilot/README.md) has **{{FINAL_FULL_ASSEMBLY_COUNT}} complete-design / {{FINAL_PILOT_ASSEMBLY_COUNT}} pilot assembly references**, **{{FINAL_PILOT_PART_GROUPS}} pilot part groups**, and **{{FINAL_EXCLUSION_COUNT}} exclusions**. Its [manifest](../gerbers/v1.1-pilot/manifest.json) records **{{FINAL_SOURCE_FILE_COUNT}} source inputs and {{FINAL_OUTPUT_FILE_COUNT}} outputs**. Pilot-vs-full comparison must prove only U6 is omitted, its 16 stencil apertures are suppressed, and all retained BOM/CPL rows and artwork match.

The retained supplier rotation profile specifies **U1 90°, U2 90°, U4 270°, U7 0°, U8 90°**; U3 remains 180° and U5 0°. These are CPL conventions, not footprint-rotation changes. U2's pin 1 is lower-left and its twelve-pad edge is at the bottom in the supplier top view. U4's black circle is the pressure port; use the separate pin-1 marker. U6 is absent from the pilot CPL; future U6 placement requires its own actual supplier-model review. [Rotation evidence](../../analysis/v1_1_release_20261012/jlc/supplier-rotation-profile.json).

Final uploaded package/placement evidence: **{{FINAL_JLC_EVIDENCE_LINK}}**. Green-mask/no-silkscreen CAM, rails and double-sided assembly disposition: **{{FINAL_CAM_STATUS}}**. Cart: **{{FINAL_CART_STATUS}}**, **{{FINAL_CART_LINK}}**. A cart entry does not qualify the physical hardware or approve factory changes. Checkout/payment is not authorized. See [FABRICATION.md](FABRICATION.md) and the [pilot acceptance procedure](../../analysis/v1_1_release_20261012/pilot-acceptance.md).

- [v1.1 / v2 checklist](TODO.md)
- [Manual KiCad review list](../../analysis/v1_1_release_20261012/manual-review-changes.md)
- [Header geometry](../../analysis/v1_1_release_20261012/headers/README.md)
- [Part identities and U7](../../analysis/v1_1_release_20261012/identities/README.md)

Historical records under `analysis/` retain intermediate parts, counts and mask choices. Use the final hashes above to identify this release.
