# v1.1 pilot fabrication and assembly intent

Current status, 15 October 2026: **engineer reroute under final manufacturing review**. The schematic circuit is unchanged. The [current review](../../analysis/v1_1_engineer_review_20261015/README.md) records the bounded fixes, checks and source identities. Use matching files from the [package manifest](../gerbers/v1.1-pilot/manifest.json). The saved JLC Y24 item is stale; supplier sign-in, reimport, fresh placement previews and factory CAM are pending. Planned quantity is **five PCBs, three assembled**. No checkout or payment has been made.

## Construction

- Two layers, **0.40 mm nominal finished FR4**, approximately **23.364 × 57.305 mm** outline envelope. CAD models 0.035 mm copper per face, 0.31 mm core and 0.01 mm mask per face. Confirm finished construction and tolerance with the fabricator.
- **ENIG, GREEN SOLDER MASK BOTH SIDES, NO SILKSCREEN.** Preserve supplied selective mask openings and ordinary-via tenting. Expose the solar ground banks, positive PTH lands and copper polarity marks. Native reference text stays on fabrication layers. Do not apply automatic mask expansion or paste reduction.
- Solar cuts are **open unplated notches**. Programming contacts are ordinary PTH holes. No edge plating or castellation process is selected.
- Use matching copper, drill, outline and mask files with the deliberate **pilot paste variant** below. Do not mix revisions. Enabled DRC includes the reviewed 0.10 mm copper process floor and 0.20 mm ordinary routed-edge minimum, with named contact/fine-pitch exceptions.

U1 uses native +0.04 mm perimeter mask expansion, preserving its copper, paste, exposed-pad mask and thermal holes. U4 and L2 use +0.05 mm. Actual plotted apertures pass the scoped 0.09 mm foreign-copper and 0.10 mm web checks. The [mechanical/mask review](../../analysis/v1_1_engineer_review_20261015/mechanics/README.md) records distances and limits. Supplier CAM must confirm registration, mask dams, tenting and thin-board processing.

## Pilot population and stencil

The native design includes **AS7331-AQFM C20482877** at U6. Initial automated assembly **omits U6 only**. Populate **C14/C23, CL05B104KO5NNNC C1525, 100 nF**, and **R27, MCU0805MD3304BP500 C4313228, 3.3 MΩ ±0.1% ±25 ppm/K**. Do not substitute an ordinary 100 ppm/K resistor.

The pilot front paste removes **exactly 16 U6 pad apertures**. All other front paste and all rear paste remain. Full-design paste is archived separately under `native/full-design-paste/`; the stencil-only derived PCB and plots are under `native/stencil/`. [Stencil proof](../gerbers/v1.1-pilot/stencil-population-proof.json). This pilot stencil is unsuitable for a later populated UV build.

U7's twelve apertures are **81% of copper-land area**, or 90% linear dimensions. Do not reduce them again. A **100 µm stencil** is the working reference, within ST's 90–150 µm recommendation; confirm paste, stencil and double-sided handling. Future AS7331 population requires separately reviewed stencil/process, actual supplier-model pin-1 orientation, MSL3 handling and sensor reflow/cleaning limits. Keep the optical aperture free of solder, flux, coatings, glue and tape. [UV assembly requirements](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).

## Part identities and placement review

Use exact MPN/LCSC identities from the generated [BOM](../gerbers/v1.1-pilot/BOM-stratolink.csv), with its matching [CPL](../gerbers/v1.1-pilot/CPL-stratolink.csv). The package has **58 full-design / 57 pilot automatic-assembly references**, **30 pilot groups** and **11 manual/DNP exclusions**. U5 is TMP117AIYBGR C2871893; U2 is RAK3172-8-SM-NI C5452091. R4 is RC0402FR-073M65L C477700; D1/D3 are PESD5V0U1BB C5272735.

Power identities: R1 **FRC0402F7504TS C3013187**, U8 **TLV8801DBVT C544879**, R24/R25 **FRC0402F4754TS C2998153**, R26 **0402WGF220JTCE C25092**, C22 **CL05B104KO5NNNC C1525**. Preserve U8 feedback before R26 and the C5 midpoint connection. U8 is now on **F.Cu at native 180°**, replacing the earlier rear placement.

**The current supplier rotation profile is a draft.** U1 and U5 rotated 180° in the reroute; U8 changed face. Draft CPL values **U1 270°, U5 180°, front U8 180°** require fresh supplier preview. U2/U4/U7 retain their native poses, but review all assembled parts after reimport. Native footprint angles and supplier CPL angles use different conventions. U4's black circle is its pressure port, not its pin-1 marker. U6 has no pilot CPL row; its new native 180° orientation requires a separate supplier check before a populated build.

Historical Y24 MPN matches and placement screenshots apply only to its earlier source. Do not treat them as verification of this board. J1/J2/J20 lost their prior exclude-position attribute in the incoming file; the final PCB and schematic restore it, and the generator retains explicit manual exclusions. The intended order remains **Standard PCBA, both sides, five PCBs / three assembled, green 0.40 mm FR4, 1 oz copper, ENIG**. Supplier rail/tab placement, final panel envelope, gold finish and handling need renewed confirmation.

## Manual assembly after reflow and cleaning

**C5 supercapacitor:** retain **DMF4B5R5G105M3DTA0**, at **(64.875, 66.007) mm on the rear, native 180°**. Fit after reflow and cleaning using the CAP-XX secondary soldering process. Pad 1 is positive, pad 2 negative and pad 3 **SC_MID**, not ground. Maximum case clearance is **2.306 mm to the outline**, **0.696 mm to AE1's rear land** and **0.920 mm to the nearest Tag-Connect hole** before placement, insulation and solder allowance. Inspect these actual gaps and measure both cells.

**J1/J2 solar panels:** each **1.0 × 2.0 mm unplated notch** seats the prepared negative terminal against its straight upper bank. Wet the GND lands on both faces; the model targets approximately 1.3 mm straight-bank overlap. Lower positives use **0.70 mm holes / 1.40 mm lands**. The display model uses 0.50 mm formed wire with insulation on the return. Measure real terminal thickness and exposed foil; model geometry does not establish strength or bend limits.

**J3/J4 programming wires:** **1.00 mm pitch, 0.50 mm holes, 0.88 mm front lands, 1.20 × 0.88 mm rear lands**, rear offset 0.12 mm inward. Solder temporary wires from the enlarged rear side. Preserve pin 1 and avoid bridging the roughly 0.12 mm land gap. These are PTH contacts, not castellated edge connectors. J20 remains an unsoldered Tag-Connect interface.

**AE1/AE2 antennas:** AE2 is at **(59.38, 33.13) mm, native 90°**, with the **48 mm GNSS wire upward**. AE1's **82 mm LoRa wire points downward**. Use straight enameled copper wire, with enamel removed at the joint. [Published starting cuts](https://stratolink.org/docs/hardware#antennas-and-suspension), measured from the feed, are 82 mm at 915 MHz, 86 mm at 868 MHz, 83 mm compromise and 48 mm GNSS L1. Record actual diameter, cut and solder exit; evaluate the completed antenna assembly. No spring or chip antenna is ordered.

The nominal GNSS wire clears the solar model by **20.54 mm**. Its model includes a small display intersection with the board surface; bend/standoff and wire diameter are not manufacturing tolerances. Keep the bridle behind and clear of the wire throughout motion. A projected string crossing alone is not a physical collision. [Native geometry and renders](../../analysis/v1_1_engineer_review_20261015/mechanics/README.md).

**H1/H2 suspension:** **2.00 mm plated holes / 3.20 mm GND rings**. Pass the thin stretchy line through both holes to form the triangular bridle. Check actual corner loading, rim wear and knot security.

## Release record and physical acceptance

Use the [current engineering review](../../analysis/v1_1_engineer_review_20261015/README.md) for strict native checks, connectivity, filled-copper review and final source identities. Use the [package manifest](../gerbers/v1.1-pilot/manifest.json), BOM, CPL and [fabrication ZIP](../gerbers/v1.1-pilot/fabrication-review.zip) together. Run `python3 hardware/pcb/verify_review_package.py` from the review checkout to verify the matching package.

The saved JLC cart item **fabrication-review_Y24**, PCB **Y24-2680969A** / PCBA **SMT026101364685-2680969A**, remains an earlier revision. Fresh upload and both-side placement review are required before approving fabrication. Preserve manual production-file and parts-placement confirmation. No checkout or payment was made; the older Y22 draft is untouched. [Historical supplier record](../../analysis/v1_1_release_20261012/as7331/jlc/README.md).

Use **`stratolink_v1_1_uv_dnp`** firmware while U6 is absent. Verify TMP117 ACK/ID/readings, unavailable UV/lux/acoustic reporting, pressure/IMU/GNSS, radio transients, solar joint and bridle security. Measure charge plateau, both cell voltages, midpoint stability, cold leakage/ESR, dark current and sunrise recovery. **Cold panel Voc/I–V and harvester input-voltage/input-power limits remain unresolved physical bounds.** A later AS7331 build also needs a validated driver, controlled optics, raw data and calibration before an ozone claim.

See [TODO.md](TODO.md), [pilot acceptance](../../analysis/v1_1_release_20261012/pilot-acceptance.md), [power review](../../analysis/v1_1_release_20261012/power/README.md) and [AS7331 requirements](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).
