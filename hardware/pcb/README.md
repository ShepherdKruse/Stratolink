# Stratolink hardware v1.1 pilot

Current status, 15 October 2026: **engineer reroute under final manufacturing review**. The schematic is unchanged. The board incorporates the reviewed reroute, with bounded corrections for connectivity, ground reference, mask clearance and assembly. See the [current engineering review](../../analysis/v1_1_engineer_review_20261015/README.md) for the change ledger, checks and source identities. The older saved JLC Y24 cart does not represent this board. Fresh supplier placement previews and factory CAM remain pending.

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. The canonical project lives in `hardware/pcb` on `alpha/hardware-v1.1`; Git retains the flown v1. Keep `lib/`, `3d/`, `sym-lib-table` and `fp-lib-table` together. Board-specific footprints retain reviewed pad geometry and mask/paste settings. Do not replace them wholesale with stock footprints. All 68 embedded footprints match their updated local library pad geometry and model attachments; all 63 model attachments resolve with the project assets and KiCad 10 standard models.

The pilot retains the **0.40 mm, two-layer board, ENIG, green solder mask on both faces, no silkscreen and tented ordinary vias**. It uses one radio, the existing GNSS/pressure/IMU parts and the flat rear capacitor. The plan is **five fabricated boards, three assembled**, followed by physical qualification before a larger batch. Source and output hashes belong to the [current review](../../analysis/v1_1_engineer_review_20261015/README.md) and [manufacturing manifest](../gerbers/v1.1-pilot/manifest.json); use matching files together.

## Current board and assembly

| Area | Configuration |
|---|---|
| GNSS | AE2 at **(59.38, 33.13) mm**, with the **48 mm wire upward** from the top-left feed. Retain the engineer's placement and reviewed ground reference. |
| LoRa | Straight enameled wire downward from AE1. Reference cuts from the feed: **82 mm at 915 MHz**, 86 mm at 868 MHz or 83 mm compromise. |
| Precision temperature | Corrected **TMP117AIYBGR C2871893** ball map at U5, address 0x48. Native placement is now 180°. |
| Microphone | MK1/R20/C13, their dedicated routing and acoustic opening removed; PB3/PB4 unused. |
| Solar mounting | Two **1.0 × 2.0 mm open unplated notches**, upper-bank GND lands on both faces, and separate lower **0.70 mm positive wire holes**. Panels stay parallel. |
| Suspension | **2.0 mm plated holes / 3.2 mm GND rings**, for the triangular string bridle. |
| Programming | J3/J4 ordinary PTH contacts: 1 mm pitch, 0.50 mm holes, 0.88 mm front lands, **1.20 × 0.88 mm rear lands** offset 0.12 mm inward. No castellations. |
| Capacitor | C5 remains the flat hand-fitted rear part, now at **(64.875, 66.007) mm**, native 180°. Its enlarged courtyard is retained in the library. |
| Cell balancing | U8 **TLV8801DBVT** and R24/R25/R26/C22 retained. U8 is now on the **front at native 180°**. |
| Mask | U1 perimeter lands use native **+0.04 mm** mask expansion; U4 and L2 use **+0.05 mm**. Copper and paste geometry are preserved. |

The [mechanical review](../../analysis/v1_1_engineer_review_20261015/mechanics/README.md) includes full assembly, front and rear native renders. The nominal GNSS wire clears the modeled solar assembly by **20.54 mm**. A triangular bridle can cross its XY projection, so keep the actual string behind the wire with space for motion. C5's maximum case clears the board edge by **2.306 mm**, AE1's rear copper land by **0.696 mm** and the nearest Tag-Connect hole by **0.920 mm**. These distances exclude hand-placement error, solder and insulation. The solar film bend, terminal thickness and wire diameter remain nominal model assumptions.

## UV circuit and pilot population

U6 is **ams AS7331-AQFM C20482877**, with separate UVA/UVB/UVC channels, 3.3 V supplies and I²C address **0x74**. C14 and C23 are **100 nF CL05B104KO5NNNC C1525**. R27 is **3.3 MΩ, ±0.1%, ±25 ppm/K MCU0805MD3304BP500 C4313228**. READY is unconnected; SYN and the address inputs are grounded for polled command-mode operation. Current positions and orientations are recorded in the native board and generated placement files, replacing earlier placement notes.

The native design contains the complete circuit. Initial automated assembly **omits U6 only**, retaining **C14, C23 and R27**. Its BOM/CPL omit U6, and its stencil removes exactly the **16 U6 paste apertures**. Full-design paste remains separate for a later reviewed population. U6 is drawn in the full assembly renders but is absent from the three pilot assemblies. [Circuit and sourcing record](../../analysis/v1_1_release_20261012/as7331/README.md).

Build **`platformio run -e stratolink_v1_1_uv_dnp`** from `firmware/` for these pilots. It leaves PB3/PB4 quiet, makes no optical I²C requests and reports UV/lux unavailable. The older `stratolink_v1_1` target expects LTR390. A populated AS7331 has **no supported flight target yet** and requires its own validated driver, power-down behavior and raw multiband telemetry. [Firmware verification](../../analysis/v1_1_release_20261012/as7331/firmware/README.md).

AS7331 supports an experimental estimate of the **ozone column above the balloon**, not calibrated concentration directly. It has no visible-light ALS channel. Its −40…85 °C operating range needs actual die-temperature verification. The manufacturer recommends incidence within ±10° and warns that visible/IR leakage can overwhelm weak UV signals. Angle control, spectral filtering, calibration and low-pressure/thermal qualification remain necessary. U6-absent pilots produce no UV or ozone data. [Primary-source requirements](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).

## Electrical identities and qualification

U5's map is **A1 SDA, A2 SCL, B1 +3.3 V, B2 GND, C1 GND, C2 grounded ALERT**. The AI grade is specified to ±0.2 °C over −40…100 °C and ±0.25 °C over −55…125 °C under its stated conditions. Sunlight and board conduction add ambient-air error. Exact retained identities include **RAK3172-8-SM-NI C5452091** at U2, **RC0402FR-073M65L C477700** at R4 and **PESD5V0U1BB C5272735** at D1/D3. [Identity review](../../analysis/v1_1_release_20261012/identities/README.md).

R1 is **7.50 MΩ FRC0402F7504TS C3013187**, with R2 at 4.22 MΩ, for a nominal **5.041 V** charge ceiling. C5 is **DMF4B5R5G105M3DTA0**: pad 1 positive, pad 2 negative, pad 3 **SC_MID**, not ground. U8 feedback joins the output to its inverting input **before R26**; R26 connects to the midpoint. R24/R25 are 4.75 MΩ, R26 is 22 Ω and C22 is 100 nF. C5 is fitted after reflow and cleaning using its secondary soldering process. [Power circuit review](../../analysis/v1_1_release_20261012/power/README.md).

Charge plateau, both cell voltages, midpoint stability, cold leakage/ESR, dark current and sunrise recovery require measurement. **Cold panel Voc/current and BQ25570 input-voltage/input-power limits remain unresolved physical bounds.** CAD cannot qualify them.

The SWD mapping remains the standard RAK3172 mapping. Use a receive-only adapter for passive J4 UART observation; an adapter transmitter can contend with the GNSS transmitter. Keep the 4.7 kΩ I²C pull-ups pending a measured 300 ns rise-time check. C8/C21 remain. [Digital review](../../analysis/v1_1_peer_review_20261014/digital/README.md), [bypass review](../../analysis/v1_1_peer_review_20261014/power/README.md).

## Manufacturing review

Enabled checks use the reviewed **0.10 mm copper process floor, 0.15 mm general clearance target and 0.20 mm ordinary routed-edge minimum**, with named fine-pitch/contact exceptions. The two intended ERC exclusions are U5 grounded ALERT and U7 SA0. Actual mask Gerbers for the repaired U1/U4/L2 apertures meet **0.09 mm aperture-to-foreign-copper** and **0.10 mm mask-web** checks. Solar polarity symbols are copper with mask openings; native silkscreen artwork count is zero. These checks do not establish controlled impedance, measured RF gain or factory CAM approval.

The package contains **58 full-design / 57 pilot automatic-assembly references**, **30 pilot part groups** and **11 manual/DNP exclusions**. J1/J2/J20 lost their exclude-position flags in the incoming board. The final PCB and schematic restore them; the generator also retains explicit manual exclusions. [BOM, CPL and fabrication package](../gerbers/v1.1-pilot/README.md).

**Supplier placement review is pending.** U1 rotated 180°, U5 rotated 180° and U8 changed face, so the previous absolute rotation profile cannot be reused unchanged. The draft supplier CPL uses **U1 270°, U5 180° and front-side U8 180°**, all requiring fresh preview confirmation. U2/U4/U7 retained native poses. U6 is omitted; its new 180° pose needs a separate supplier check before population.

The old JLC item **fabrication-review_Y24**, PCB **Y24-2680969A** / PCBA **SMT026101364685-2680969A**, contains an earlier board. Its price and previews are historical, not approval of this reroute. Sign-in, reimport, both-side placement review and factory review of rails/tabs, thin-board handling and mask/stencil disposition are outstanding. No checkout or payment has been made.

- [Fabrication and manual assembly instructions](FABRICATION.md)
- [v1.1 / v2 checklist](TODO.md)
- [Current engineering review and change ledger](../../analysis/v1_1_engineer_review_20261015/README.md)
- [Pilot acceptance procedure](../../analysis/v1_1_release_20261012/pilot-acceptance.md)
- [Solar 3D model assumptions](3d/solar/README.md)

Historical analysis files retain earlier placements and supplier previews. Use the current review and package manifest to identify this board.
