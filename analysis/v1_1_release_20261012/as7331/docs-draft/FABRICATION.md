# v1.1 pilot fabrication and assembly intent

**DRAFT — prepared for the AS7331 update; canonical promotion and final supplier review are not yet claimed.** Final promotion/review: **{{FINAL_PROMOTION_STATUS}} / {{FINAL_REVIEW_STATUS}}**. Planned quantity is **five PCBs, three assembled**. Final JLC selection: **{{FINAL_JLC_SELECTION_STATUS}}**. Cart status/link: **{{FINAL_CART_STATUS}} / {{FINAL_CART_LINK}}**. A reviewed cart draft is authorized; checkout/payment is not.

## Board construction and finish

- Two copper layers, **0.40 mm nominal finished FR4**, existing 23.36 × 57.30 mm outline envelope. CAD models 0.035 mm copper per face and a 0.31 mm core plus 10 µm solder mask per face; confirm final construction and tolerances with the fabricator.
- **ENIG, GREEN SOLDER MASK BOTH SIDES, NO SILKSCREEN.** Remove the former whole-board openings. Preserve supplied selective mask apertures and ordinary-via tenting; expose all solar soldering banks and positive PTH lands. Native reference/property text lives on fabrication layers, not silkscreen. Do not apply automatic mask expansion without approval.
- Ordinary routing, PTH and NPTH processes. Solar cuts are **open unplated notches**. Programming contacts are ordinary PTH holes. No edge plating or castellation process is selected.
- Solar polarity marks are copper with local mask openings. Final local routing and label scope: **{{FINAL_UV_ROUTING_AND_LABEL_SCOPE}}**. Silkscreen artwork count: **{{FINAL_SILK_WARNING_COUNT}}**; final mask/legend disposition **{{FINAL_SILK_CAM_STATUS}}**.

Use the matching source-derived copper, drills, outline, mask and silk with the deliberate **pilot** paste variant described below. Do not mix revisions or substitute full-design paste for the pilot stencil. Enabled rules use the reviewed 0.10 mm copper process floor and 0.20 mm ordinary routed-edge minimum, with explicit contact/fine-pitch exceptions. CAD checks do not constitute CAM acceptance of this thin board and its mask apertures.

## Pilot population and stencil

The native PCB and schematic contain a fully designed **AS7331-AQFM C20482877** circuit at U6. The initial automated-assembly BOM/CPL **omit U6 only**. Populate **C14 and C23, CL05B104KO5NNNC C1525, 100 nF**, and **R27, MCU0805MD3304BP500 C4313228, 3.3 MΩ ±0.1% ±25 ppm/K 0805**. Do not substitute an ordinary 100 ppm/K resistor. The local regulator rails and I²C pull-ups remain populated.

The pilot F.Paste file removes **exactly the 16 U6 pad apertures**. Remaining front paste and all rear paste are retained. Full-design paste is archived in `native/full-design-paste/`; the export-only stencil PCB and plots are under `native/stencil/`. The [stencil proof](../gerbers/v1.1-pilot/stencil-population-proof.json) and [package manifest](../gerbers/v1.1-pilot/manifest.json) identify both variants. **Never use this pilot stencil for a later fully populated UV build.** Bare copper lands remain available for a separately reviewed U6 installation.

Mask and paste apertures serve different purposes. U7's twelve apertures are already **81% of copper-land area**, or 90% linear dimensions. Do not apply a second global reduction. A **100 µm stencil** is the working reference, within ST's 90–150 µm recommendation; confirm paste, stencil and double-sided handling. For future AS7331 population, the derived 0.35 mm square lands and 0.30 mm paste apertures give a 0.75 aperture-area/wall-area ratio at 100 µm, versus 0.625 at 120 µm. This is an engineering screen, not a manufacturer-qualified land/stencil recommendation. [UV assembly review](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).

A later populated U6 requires actual supplier-model pin-1 review, an appropriate stencil/process, MSL3 handling and the sensor's reflow limits. Keep the optical aperture free of solder, flux, coatings, glue and tape; follow manufacturer cleaning guidance. It also requires a validated AS7331 driver and optical characterization. The DNP pilot does not perform UV or ozone measurements.

## Retained assembly identities and orientations

U5 is **TMP117AIYBGR C2871893**; D1/D3 are **PESD5V0U1BB C5272735**. R4 is **RC0402FR-073M65L C477700**, retaining 3.65 MΩ, ±1%, ±100 ppm/°C and 0402 lands. U2 is **RAK3172-8-SM-NI C5452091**, the manufacturer's equivalent hardware for the former 9-label orderable. Preserve its native 180° placement. These are exact metadata/orderable changes, not new package geometries.

Power components are **R1 FRC0402F7504TS C3013187, 7.50 MΩ; U8 TLV8801DBVT C544879; R24/R25 FRC0402F4754TS C2998153, 4.75 MΩ; R26 0402WGF220JTCE C25092, 22 Ω; C22 CL05B104KO5NNNC C1525, 100 nF**. U8 stays on B.Cu at (55.65, 36.10) mm, native 0°. Preserve the C5 midpoint circuit and U8 feedback before R26. D3.1/J4.1 use local 0.25 mm thermal gaps/bridges.

Supplier CPL values remain **U1 90°, U2 90°, U4 270°, U7 0°, U8 90°; U3 180°, U5 0°**. They come from numbered-pad/package checks and actual supplier reimport; the historical input CPL alone is not a post-CAM rotation record. U2 has pin 1 lower-left with its twelve-pad edge at the bottom in the north-up top view. U8's bottom view has three leads right, two left, pin 1 lower-right. U4's black circle is its pressure port; its separate pin-1 marker is upper-left. These CPL corrections do not rotate native footprints. U6 has no pilot CPL row; its future supplier rotation remains unqualified. [Supplier profile](../../analysis/v1_1_release_20261012/jlc/supplier-rotation-profile.json).

Final full preview, R27/C23/C14 placement and allocation: **{{FINAL_PLACEMENT_REVIEW_STATUS}}**. Search stock is not a reserved allocation. Confirm final two-sided assembly and panel rails without automatic acceptance of supplier geometry changes. Factory CAM/rails/mask-aperture acceptance: **{{FINAL_CAM_STATUS}}**.

## Manual assembly after reflow and cleaning

**C5 supercapacitor:** retain `DMF4B5R5G105M3DTA0`. Install after board reflow and cleaning using the CAP-XX secondary soldering process; it is not a normal reflow component. Check **pad 1 positive, pad 2 negative, pad 3 physical midpoint / SC_MID**. Do not treat the center as ground. Measure both cells before flight.

**J1/J2 solar panels:** each **1.0 mm-wide × 2.0 mm-deep unplated notch** seats the prepared negative terminal against its straight upper bank. Wet the GND lands on both faces; the model targets about 1.3 mm straight-bank overlap. Lower positives use **0.70 mm holes / 1.40 mm lands**. The model uses 0.50 mm solid formed wire with insulation on the return. Measure real terminal thickness and exposed foil; the photo-scaled model does not establish strength or bend limits.

**J3/J4 programming wires:** **1.00 mm pitch, 0.50 mm holes, 0.88 mm front lands, 1.20 × 0.88 mm rear lands**, rear offset 0.12 mm inward. Solder temporary wires from the enlarged rear side. Preserve pin 1 and avoid bridging the approximately 0.12 mm adjacent-land gap. These are PTH contacts, **not castellated edge connectors**, and are excluded from automatic placement.

**AE1/AE2 antennas:** straight enameled copper wire, enamel removed only at the joint. [Published starting cuts](https://stratolink.org/docs/hardware#antennas-and-suspension), measured from the feed, are **82 mm at 915 MHz, 86 mm at 868 MHz, 83 mm compromise, 48 mm GNSS L1**. The models use 82/48 mm. Record actual diameter, cut and solder exit; evaluate the completed RF/GNSS assembly. No spring or chip antenna is being ordered.

**H1/H2 suspension:** **2.00 mm plated holes / 3.20 mm GND rings**, unchanged centers. Pass the actual thin stretchy line through both to form the triangular bridle. Check corner loading and rim wear physically. J20 remains an unsoldered Tag-Connect interface.

## Final record and physical qualification

Final DRC: **{{FINAL_DRC_RESULT}}**. ERC: **{{FINAL_ERC_RESULT}}**, with only the **two** documented U5 ALERT / U7 SA0 exclusions; AS7331 READY is explicitly unconnected. Independent native/schematic/paste review: **{{FINAL_INDEPENDENT_REVIEW_LINK}}**. Counts: **{{FINAL_FULL_ASSEMBLY_COUNT}} full-design / {{FINAL_PILOT_ASSEMBLY_COUNT}} pilot references**, **{{FINAL_PILOT_PART_GROUPS}} pilot part groups**, **{{FINAL_EXCLUSION_COUNT}} exclusions**. The [README](README.md#rules-evidence-and-supplier-state) pins source hashes; the manifest pins all matching outputs.

| Package artifact | Final SHA-256 |
|---|---|
| [BOM](../gerbers/v1.1-pilot/BOM-stratolink.csv) | `{{FINAL_BOM_SHA256}}` |
| [CPL](../gerbers/v1.1-pilot/CPL-stratolink.csv) | `{{FINAL_CPL_SHA256}}` |
| [Fabrication ZIP](../gerbers/v1.1-pilot/fabrication-review.zip) | `{{FINAL_FABRICATION_ZIP_SHA256}}` |
| [Manifest](../gerbers/v1.1-pilot/manifest.json) | `{{FINAL_MANIFEST_SHA256}}` |

Uploaded artifact identity and supplier evidence: **{{FINAL_JLC_EVIDENCE_LINK}}**. Do not retain an older draft's ZIP/BOM/CPL merely because its filename matches. Cart status: **{{FINAL_CART_STATUS}}**; checkout/payment is not authorized.

Use **`stratolink_v1_1_uv_dnp`** firmware while U6 is absent. Verify direct TMP117 ACK/ID/readings, unavailable UV/lux/acoustic reporting, pressure/IMU/GNSS and radio transients. Measure solar joint/bridle security, charge plateau, both cell voltages, midpoint stability, cold leakage/ESR, dark current and sunrise recovery. **Cold panel Voc/I–V and harvester input-voltage/input-power limits remain unresolved physical bounds.** CAD cannot qualify them. A later AS7331 installation also needs a driver, controlled optics, raw data and calibration before any ozone claim.

See [TODO.md](TODO.md), [pilot acceptance](../../analysis/v1_1_release_20261012/pilot-acceptance.md), [power review](../../analysis/v1_1_release_20261012/power/README.md) and [AS7331 review](../../analysis/v1_1_release_20261012/as7331/README.md).
