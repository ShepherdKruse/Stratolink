# Stratolink hardware — v1.1 pilot

**Verified pilot design and manufacturing review package.** The canonical files below pass native and independent checks and are open in KiCad for review. Supplier allocation, placement and CAM remain pending; no order has been placed.

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. The canonical hardware project lives here on `alpha/hardware-v1.1`; Git retains the flown v1 design. Keep the project-local `lib/`, `3d/`, `sym-lib-table` and `fp-lib-table` together. Board-specific release footprints preserve the deliberate local geometry and agree with the placed board; avoid replacing them through a blanket stock-library update.

The pilot keeps the 0.40 mm, two-layer board, one LoRa radio, existing GNSS/pressure/UV/IMU parts and the flat rear capacitor. Its finish is **ENIG with no solder mask on either face and no via tenting**. Full-board F.Mask/B.Mask openings express that intent; stencil paste remains a separate, selective layer. The current plan is **five fabricated boards, three assembled**, followed by physical checks before a larger batch.

## Current pilot changes

| Area | Pilot configuration |
|---|---|
| Precision temperature | U5 is **TMP117AIYBGR, LCSC C2871893**, matching the actual flown order. The repaired YBG ball map and local routing remain. Earlier N-grade metadata was inaccurate. |
| Microphone | MK1, R20, C13 and their dedicated routes/acoustic opening are removed. U2 PB3/PB4 are unused. |
| Solar mounting | Each side has a 1.0 × 2.0 mm open **unplated** notch with GND lands on both faces, plus a separate lower 0.70 mm positive wire hole. Both panels stay in parallel. The negative terminal seats against the straight upper bank and is soldered on both faces. |
| Suspension | Two 2.0 mm plated holes with 3.2 mm grounded rings retain the existing centers and support the triangular string bridle. |
| Programming access | J3/J4 retain 1.00 mm pitch, 0.50 mm holes and 0.88 mm front lands. The rear lands are 1.20 × 0.88 mm and offset 0.12 mm inward for temporary wire soldering. Pin 1 remains rectangular. |
| Antennas | AE1 and AE2 are hand-formed straight enameled copper wire. Reference cuts from the feed are 82 mm for 915 MHz LoRa and 48 mm for GNSS L1; 86 mm is the documented 868 MHz option, 83 mm the compromise. |
| U7 assembly | Existing copper lands retained; each paste aperture is 90% of copper dimensions, **81% of copper area**. Perimeter escapes and bottom routing clear the central top-side underside. Body/central keepouts preserve this geometry. |
| Ground and small routing | Redundant GND pour and the tiny duplicate VSTOR segment are removed; intentional thermal/direct connections, near-edge routes and wire-antenna envelopes are reconciled. |
| Part/library identities | Exact supplied orderables replace stale comments, including D1/D3 **PESD5V0U1BB C5272735**. U6 footprint metadata and U1 exposed-pad numbering agree with physical geometry. |

The U5 ball map is A1 SDA, A2 SCL, B1 +3.3 V, B2 GND, C1 GND for address `0x48`, and C2 unused ALERT grounded as TI permits. The AI grade does not promise ±0.1 °C throughout the flight envelope: TI specifies ±0.2 °C over −40…100 °C and ±0.25 °C over −55…125 °C under its stated conversion conditions. Ambient-air error also depends on mounting, sunlight and conduction. See the [identity and assembly audit](../../analysis/v1_1_release_20261012/identities/README.md).

The [solar 3D models](3d/solar/README.md) show the intended assembly using photo-scaled 94 × 75 mm panels, a straight root, curved film and formed positive wires. Terminal thickness, prepared wettable area, strength and actual wire dimensions need physical confirmation. The model is an assembly aid, not a measured joint rating.

## Verified integrated power design

The authored power candidate is frozen: R1 is **7.50 MΩ, FRC0402F7504TS C3013187**, R2 remains 4.22 MΩ, and the CAP-XX active midpoint circuit uses TLV8801, two 4.75 MΩ resistors, 22 Ω output isolation and 100 nF bypass. U8/R24/R25/R26/C22 sit on the upper-left rear, clear of the flat capacitor. The capacitor keeps pad 1 positive and pad 2 negative; its physical center terminal, pad 3, becomes `SC_MID`. Feedback connects directly from amplifier output to its inverting input **before** the 22 Ω resistor. The circuit is powered by the capacitor stack.

The routed candidate replaces only the required VSTOR ADC sense branch and adds the balancing paths. D3.1 and J4.1 use explicit **0.25 mm thermal gap and bridge width**; connection style and the two-spoke minimum remain. Integration retains the enlarged J4 lands. The final combined candidate independently preserves all retained physical pad connections and geometry.

The [power review](../../analysis/v1_1_release_20261012/power/README.md) documents the selected charge screen, tolerance assumptions and startup/stability limits. The integrated schematic, physical-pad connectivity, clearances and rule checks pass; the preflight manufacturing export contains the expected five added parts. Cold charge plateau, both cell voltages and balancer stability require measurement. **Solar input voltage/current bounds remain unresolved:** the panel label and existing telemetry do not establish that BQ25570's voltage and input-power limits are met.

## Rules and release state

Copper clearance, routed-edge clearance and annular-ring checks are enabled. The reviewed rule set uses a 0.10 mm process floor, a 0.15 mm general clearance target and a 0.20 mm routed-edge minimum, with named local constraints for fine-pitch/contact geometry. The U7 SCL passage at U6 pad 6 has a specific 0.12 mm constraint and 0.128 mm measured clearance. Rules are recorded in the project and `.kicad_dru`; they do not imply that all historical routes meet the old blanket 0.20 mm preference. Only the inapplicable solder-mask-bridge category is disabled for the bare finish. Exposed-copper legend advisories remain visible and require CAM disposition.

The integrated candidate has **zero opens, zero schematic parity/library mismatches, and four retained silk-over-exposed-copper warnings**. Filtered ERC is zero; its raw two errors and one warning are retained under exactly three documented grounded-output/address-strap exclusions. No broad ERC severity is relaxed. Independent native comparison preserves all 232 old pad islands, copper polygons and drills, adds 13 pads, and confirms capacitor polarity and feedback topology. Native schematic exports account for all 233 connected/unused pin records. See [scope and thermal proof](../../analysis/v1_1_release_20261012/manufacturing/final-scope-verification.json), [physical connectivity](../../analysis/v1_1_release_20261012/manufacturing/final-native-connectivity-review.json), and [ERC/geometry verification](../../analysis/v1_1_release_20261012/erc/final-cleanup-verification.json).

| Verified canonical file | SHA-256 |
|---|---|
| PCB | `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15` |
| Schematic | `044984037a7346adc92ee9ea142e6c285ee7f6b66efc87e0a1ad195495379cc9` |
| Project | `79a2c0d01611c7ea7054cd9dbc685187b28fb4ac8792468a15d2bba821ac0ea7` |
| Rules | `565bbdcb4ddc03de2a7bc3cdc45d57a8acd92d2e53a8eac092e0bd5a04861e0b` |

The canonical-source export passes population checks: **56 assembly references, 30 part groups, 10 intentional exclusions**. U7's 12 final paste apertures retain 81% copper-land area. The [manufacturing package](../gerbers/v1.1-pilot/README.md) and [complete source/output hash manifest](../gerbers/v1.1-pilot/manifest.json) are available. The canonical CAD hashes are unchanged after reopening the PCB and native 3D viewer.

The final fabrication ZIP has been uploaded to the authorized JLC draft. Five boards/three assembled, 0.4 mm, ENIG and untented vias are configured, with manual CAM and placement confirmation. The actual assembly flow accepts the final BOM/CPL and the three-board quantity, detecting **56 references: 53 confirmed and three inventory shortages**. R4 needs 20 including feeder allowance, with zero stock; U2 needs three, with one available; U6 needs three, with zero available. R6's earlier public-tool concern is resolved: its 20-piece feeder quantity is available. The public tool's header/quantity defects do not affect this assembly import. Final shortage resolution, placement preview and CAM remain **not confirmed**. The authorized supplier work is a draft; checkout/payment has not been authorized or performed. See [FABRICATION.md](FABRICATION.md) for the exact fabrication and assembly intent.

Build the matching firmware with `platformio run -e stratolink_v1_1` in `firmware/`. This variant leaves PB3/PB4 quiet and reports acoustic unavailable; the existing `stratolink` environment retains v1 microphone support. Verify corrected TMP117 ACK/device ID/readings, remaining sensors, GNSS/radio power transients, solar mounts, suspension and cold/dark recovery on the assembled pilots. Physical qualification remains separate from CAD checks.

- [v1.1 / v2 checklist](TODO.md)
- [Fabrication and assembly instructions](FABRICATION.md)
- [Header geometry and checks](../../analysis/v1_1_release_20261012/headers/README.md)
- [Part identities and U7 conformity](../../analysis/v1_1_release_20261012/identities/README.md)
- [Power and storage review](../../analysis/v1_1_release_20261012/power/README.md)
- [Manufacturing export method](../../analysis/v1_1_release_20261012/manufacturing/README.md)

Historical change records remain under `analysis/`; this canonical pilot record supersedes their intermediate mask choices, part names, counts and release status.
