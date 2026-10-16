# v1.1 final sweep, 16 October 2026

The reviewed pilot files and JLC draft are ready for the user's ordering decision. The AS7331 sourcing inquiry has been sent, and timing will decide whether the first three assemblies include U6. No PCB or component order has been submitted. Factory CAM and manual production-file/placement approval remain pending.

## What changed in this sweep

The working PCB had lost one 0.20 mm rear VSTOR diagonal. This disconnected R22's upper voltage-sense input from the storage rail, leaving the PA10 divider unable to measure storage voltage correctly. The exact original segment was restored. The main storage rail and separate midpoint-balancer supply were still connected.

Strict mask-bridge checking and the 0.09 mm mask-to-foreign-copper rule were restored. One obsolete LTR390 ERC exclusion was removed. The user's schematic rearrangement and five hidden fabrication values are preserved. No footprints were moved and no new routing was introduced. Relative to the previously committed, engineer-rerouted board, the repaired PCB differs only in those five fabrication-field visibility flags. The missing segment was an uncommitted regression; it does not appear as new routing in the Git diff.

| Final input | SHA-256 |
| --- | --- |
| PCB | `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13` |
| Schematic | `092ddb3451545cc6f7d7d64d8c02c933e89a40acb6897d865e3a8936d54e21fb` |
| Project | `c9be5b22927d7fe889188023e69f6e774e808aa79d4ea13eb1b2ddc348ffe2f9` |

`source-before/` preserves the defective working files for evidence only. Open the current files in `hardware/pcb/` or the refreshed download ZIP to review the repaired board.

## Independent checks

- [Electrical](electrical/README.md): fresh strict DRC has **0 violations, 0 opens and 0 schematic mismatches**. ERC has **0 unexcluded findings and 2 documented exclusions**. The separate filled-copper graph finds no foreign-net overlaps, disconnected pad nets or unanchored assigned-net copper. All 84 focused pin checks pass. All 66 schematic components, 59 nets and 247 pin/net/role entries match the frozen circuit.
- [Mechanical and manufacturing](mechanical/README.md): all 68 local footprints and 63 model attachments resolve; source geometry, outline, holes, zones and model transforms retain the reviewed design. Fresh mask geometry passes the scoped checks. No silkscreen artwork exists. New front, rear and full-assembly renders were inspected.
- [Population, RF and power](population/README.md): all **57 fitted references, 30 MPN groups, 41 top and 16 bottom placements** reconcile to exact MPN/LCSC/footprint/side data. All seven populated IC previews were rereviewed. U8 retains supplier CPL **90 degrees**, with three leads right and pin 1 lower-right. U6 alone is omitted; C14/C23/R27 stay fitted.
- [Package proof](package-verification.json): both variants bind all **166 current manufacturing inputs** and complete output inventories. The UV-omitted BOM/CPL and native positions are byte-identical to the corrected Y25 package; all **17 fabrication/stencil files** match after removal of creation timestamps only. The populated variant adds U6 and its **16 front-paste apertures**, with all retained BOM/CPL rows and other fabrication geometry unchanged.
- [Download checks](../../hardware/downloads/README.md): both refreshed archives pass byte/member verification and fresh KiCad extraction checks for 68 footprints and 63 model attachments.

## Saved JLC draft

The final saved item is **fabrication-review_Y26**, PCB **Y26-2680969A**, PCBA **SMT026101664930-2680969A**. JLC advanced the identifiers when the reviewed Y25 edit was saved; no new Gerber or BOM substitution was made. The original uploaded geometry and corrected CPL remain valid by the exact comparison above. Remarks still name the original `25b201eb` source, which is physically equivalent to the repaired current source. A [reference update](inquiry/reference-update.md) was sent in the same sourcing thread.

Saved settings: **five PCBs, three assemblies; Standard PCBA, both sides; 0.40 mm FR4 TG135, 1 oz copper, green mask, ENIG 1 microinch, no silkscreen artwork; tented vias**. Aerospace product type retains JLC's required four-wire Kelvin test. Generic silkscreen color reads White, but the actual two legend Gerbers are empty and the remark explicitly says NO SILK. Rails produce a 71.36 × 71.30 mm supplier envelope around the 23.36 × 57.30 mm board. Factory tab placement must preserve the solar notches and suspension holes.

Manual production-file and placement confirmation remain enabled, with manual approval/no automatic changes required in the saved remarks. Existing automatic-confirmation settings were not changed. The unique selected BOM capture passes all 57 reference checks. The grouped cart summary repeats some designators; this is not evidence of extra actual placements. Require the same unique 57-reference population in the final factory production files. Some supplier product-description text displays a translation placeholder; the edit form saved the custom description “Balloon atmospheric sensor and telemetry PCB.” Verify the human-readable description again at checkout.

Current quote, observed 16 October:

| Item | USD |
| --- | ---: |
| PCB | 70.63 |
| Assembly, including selected components | 262.00 |
| Merchandise total | 332.63 |
| DHL Express DDP estimate, 2–4 business days | 31.59 |
| Current coupon | -9.00 |
| Displayed cart subtotal | **355.22** |

The draft estimates **20 October dispatch**, with 24-hour PCB production and 3–4-day assembly. It is not a delivery promise; order timing, component availability and factory review can move it. Assembly offered a 2–3-day option for **$49.63 extra**; it was not selected. Manual-review assembly-remark extras are expressly excluded from the displayed total, and final checkout charges must be checked. No payment was made.

[Live cart](https://cart.jlcpcb.com/shopcart/cart). Fresh evidence is under `jlc/`: final PCB/assembly settings, individual selected rows, front/rear placement previews and quote. The captured supplier preview and prior IC closeups do not replace factory CAM or inspection of soldered boards.

## UV decision

The [inquiry](inquiry/sent.md) asks JLC for the earliest dispatch with and without AS7331, faster authorized stock, required attrition quantity, all added costs, conflicting consignment fees and MSL3 optical-package handling. A later search found no reply yet. The current cart remains UV-omitted while the quote is pending.

- **Current pilot:** [UV-omitted package](../../hardware/gerbers/v1.1-final-20261016/README.md), 57 references. C14/C23/R27 fitted; U6 omitted and no paste on its sixteen lands.
- **Conditional UV build:** [populated package](../../hardware/gerbers/v1.1-final-uv-20261016/README.md), 58 references. Prepared for AS7331-AQFM C20482877. Confirm exact sourced order code, native-to-supplier U6 pin-1 orientation, stencil and optical handling before importing. AQFT sourcing would require updating the exact assembly identity and regenerating the BOM. Do not use the UV-omitted stencil with a populated U6 BOM.

The populated export is prepared for supplier review, not released to manufacture. Firmware, optics and calibration must also be validated before flight or an ozone claim.

## Limits carried into the pilots

No new order-blocking parts mismatch was found. These remain development boards, with physical qualification open:

- Measure cold panel Voc, source I–V and VIN waveforms, including MPPT open-circuit sampling. The two 4.8 V/50 mA panel nameplates imply 0.48 W, above BQ25570's 0.40 W recommended input. Actual cold Voc may exceed its 5.1 V recommended or 5.5 V absolute input limits; neither the nameplate nor MPPT establishes compliance.
- Measure both capacitor cells, midpoint-balancer startup/stability, charge ceiling, cold leakage/ESR and sunrise recovery. Typical inductor-current and MLCC-bias data do not guarantee cold margins.
- Measure local GNSS/radio supply transients and actual antenna/RF performance. The existing RF geometry has not been qualified as 50 ohms.
- Check real solar-terminal fit, solder fillets, C5 insulation clearance and bridle load/wear. Rendered geometry is not a strength or altitude test.

These bounds are quantified in the linked reports and [pilot acceptance checklist](../v1_1_release_20261012/pilot-acceptance.md). They are separate from the passing native/manufacturing checks.

## Reproduce the recorded-file checks

```sh
python3 analysis/v1_1_final_sweep_20261016/verify.py
python3 hardware/downloads/build.py --check
```

The verifier rebases historical absolute paths to this checkout. It checks exact source, artifact, BOM/CPL, stencil and captured supplier identities. It does not rerun KiCad, query the mutable cart or certify physical behavior. Native command records and analysis reproduction instructions are in each independent report. Historical reviews retain their original hashes and are not relabeled as checks of the new source.
