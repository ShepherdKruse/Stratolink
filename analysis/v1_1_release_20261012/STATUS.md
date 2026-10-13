# v1.1 canonical pilot verified; supplier review in progress

Canonical project: `hardware/pcb`, branch `alpha/hardware-v1.1`. Baseline
`5997979` is frozen in `baseline.json`; hashes protect all 100 unrelated tracked
changes. The user authorized minimum v1.1 changes, manufacturing exports and a
JLC draft for **5 PCBs / 3 assembled**. Checkout/payment is not authorized.

## Verified in scratch

- **Headers:** rear lands enlarged to 1.20 × 0.88 mm, with unchanged 0.50 mm
  holes, 1 mm pitch and front lands. Four back-layer routes adjusted and two
  transitions added. A further 0.010 mm shift clears the adjacent route and via
  at the 0.15 mm target. JLC requires at least 0.6 mm thickness for castellations
  and plated edges, so ordinary through-holes retain the lighter 0.4 mm board.
- **Part identities:** actual shipped JLC selections recovered. TMP117AIYBGR
  (C2871893), PESD5V0U1BB protection diodes and the four 1 MΩ resistors replace
  stale descriptions. No substituted temperature-sensor package. Exact placed
  footprints are frozen as local release variants, with zero library or
  schematic-parity mismatches.
- **Rules:** clearance, edge and annular checks enabled. The normal routing
  target is 0.15 mm, above the 0.10 mm process floor. Narrow component-specific
  exceptions describe the actual fine-pitch geometry. Integrated headers and
  identities pass native refill/DRC with zero opens, zero parity findings and
  four existing bare-board legend warnings.
- **Exports:** the read-only generator checks matching PCB/schematic supplier
  fields, population exclusions, full-board negative-polarity mask openings,
  drills and native placements. The historical input CPL establishes baseline placement centers
  and rotation conventions, not the supplier's post-CAM orientations; raw footprint
  anchors would have misplaced several imported packages.

## Integrated design promoted; supplier review remains

- **U7:** the frozen candidate reduces stencil aperture area to 81% and removes
  top copper from the unsupported central body area. It passes independently
  and together with the headers: zero opens/parity findings, four unchanged
  bare-board legend advisories. Final power integration passes the same checks.
- **Storage:** integrated a CAP-XX-style active midpoint follower while retaining the
  flat on-hand 1 F capacitor. Selected parts are TLV8801DBVT, two 4.75 MΩ
  resistors, 22 Ω output isolation and 100 nF bypass. Changed R1 to an obtainable
  7.50 MΩ part. The authored candidate is routed and frozen at PCB `3bf0023e…`;
  final integrated PCB `490af47d…` passes native and independent review.
  D3.1/J4.1 alone receive 0.25 mm thermal gap/bridge overrides, with the existing
  two-spoke minimum preserved. All 232 retained physical pads preserve copper,
  drills and connected pad sets; 13 new pads and the midpoint connection match
  the intended circuit. Independent native schematic exports account for all
  233 pin records, with only the intended VBAT net rename.
- **ERC:** the reviewed cleanup freezes actual embedded symbols, corrects
  imported electrical pin types and explicitly marks unused pins. It preserves
  all physical nets and raw evidence, with three narrowly documented inherited
  grounded-output/address-strap findings. Final filtered ERC is zero; raw two
  errors and one warning remain under exactly three exclusions. Refilled
  before/after scratch copies preserve authored geometry and every fill polygon.
- **Final integration:** native and independent checks pass with four retained
  silk warnings, zero opens/parity/library/thermal findings. The verified CAD is
  promoted to `hardware/pcb`; README/FABRICATION/TODO are updated. Canonical PCB
  and native 3D are open in KiCad, and all source hashes remain unchanged.
- **Final exports:** [the package](../../hardware/gerbers/v1.1-pilot/README.md)
  is generated from canonical CAD. Its [manifest](../../hardware/gerbers/v1.1-pilot/manifest.json)
  pins 160 actual source/library/model inputs and 28 manufacturing outputs,
  including the BOM, CPL, Gerbers, separate drills and fabrication ZIP. The
  source-input list excludes interpreter/macOS cache artifacts. The earlier scoped
  cache-manifest correction did not regenerate or change any manufacturing byte;
  [its audit](manufacturing/cache-input-scope-correction.json) records original
  export-generator and current corrected-generator hashes separately.
  The later [supplier-rotation correction](manufacturing/rotation-correction-before/correction-report.json)
  changes only CPL rotations and associated audit/documentation/profile data;
  all 24 retained outputs, including BOM, native files and fabrication artwork,
  remain byte-identical. Both operations retain separate provenance.
- **Firmware metadata:** the explicit v1.1 variant now uses the new nominal
  5.041 V / 9.55 J values; v1 retains 5.363 V / 11.2 J. Diagnostic VBAT_OK labels
  are corrected to nominal 3.510/2.510 V. Microphone presence does not select the
  divider model. Runtime power policies are unchanged; the v1.1 build and four
  preprocessing checks passed. All 100 pre-existing unrelated tracked changes
  remain byte-identical to the baseline.

## Supplier workflow

The shipped order W2026030801021565 confirms five boards / three assembled,
0.4 mm, 1 oz, ENIG 1 µin and assembly on both sides. Its mask was green; this
revision deliberately removes mask on both faces.

A preliminary geometry package was uploaded to the signed-in JLC quote earlier.
JLC detects **23.36 × 57.30 mm**. Standard two-sided assembly adds a factory
panel of **71.36 × 71.30 mm**, as in the prior order. The draft is set to
0.4 mm, ENIG, untented vias, five boards / three assembled, with production-file
and placement confirmation requested and automatic confirmation disabled.
The displayed preliminary PCB price was $55.62 before assembly/shipping; this
is not the final quote. The final source-derived fabrication ZIP is now uploaded
with five boards/three assembled, 0.4 mm ENIG, untented vias and manual CAM and
placement confirmation configured. Final assembly import is complete; shortages and supplier approval remain.
No new cart item or order has been submitted.

The final BOM and CPL are uploaded to the actual assembly flow for three boards.
It detects 56 references: 53 confirmed and three inventory shortages. R4
C2766827 requires 20 including feeder allowance, with stock 0; U2 C18548052
requires 3, with stock 1 (short 2); U6 C492374 requires 3, with stock 0 (short 3).
R6 C423131 is confirmed with its 20-piece feeder quantity available. The actual
assembly flow accepts quantity 3 and has no extra header row; the earlier public
BOM tool defects are not current assembly blockers. See
[jlc/assembly-bom-match.txt](jlc/assembly-bom-match.txt).

The source-derived export has 56 assembly references, 30 part groups and 10
intentional exclusions; U7 has 12 paste apertures at 81% area. Shortage resolution,
missing-part placement and final CAM review remain pending. No substitute is accepted
by default and no component reservation is implied. The ordinary assembly-terms
step is within the authorized draft workflow; checkout/payment remains outside
scope.

## Actual supplier placement correction

The partial preview includes all 53 in-stock references; exactly R4/U2/U6 are
unavailable. Historical CPL equality only reproduced the repository's v1 input,
not JLC's final post-CAM placement. The actual preview revealed four supplier
rotation differences. Native numbered lands, manufacturer drawings and model
markers establish the required orientations. Reimported CPL files confirm
**U1 90°, U4 270°, U7 0°, U8 90°**; U3 stays 180° and U5 stays 0°.
U4's black circle represents its pressure port; its separate pin-1 marker is
upper-left in the correct top view. All XY centers, sides and CAD remain unchanged.
The [profile](jlc/supplier-rotation-profile.json) links the independent reviews
and saved before/after screenshots. The final tested CPL is
`eb8ef43bb3b1a6ee0b1efc3f3c1280f519686b6ba1fda44e61ace8cc6c4d1069`.
The actual final package BOM/CPL has been reimported, with 53 placements selected
and exactly R4/U2/U6 unavailable; [the final import record](jlc/final-package-import-selection.json)
captures that state. The canonical BOM retains all 56 assembly references.

The [auto-saved draft](https://cart.jlcpcb.com/smt-order/?pcbFileNo=273e56f80db84247a68fcd5556d381e6)
is for review only. Its displayed partial quote was $286.16: $55.57 PCB plus
$230.59 assembly, excluding R4/U2/U6, shipping and any additional checkout charges.
This is not the price of a complete payload build. No new cart item, reservation,
order or payment was submitted. No-mask processing still requires explicit CAM
acceptance; the public color dropdown's Green label does not establish acceptance.

## Physical limits that CAD cannot close

- Lowering the charge ceiling and balancing cells require pilot validation of
  both cell voltages, startup, capacitive-load stability, leakage and cold ESR.
- Historical solar telemetry reaches 5.538 V, above the BQ25570's recommended
  input ceiling. This is uncalibrated ADC evidence, not proof of actual pin
  overstress. Cold panel I–V / Voc and direct input measurements remain required.
- No unbuilt board can be physically smoke-tested or flight-qualified. Sensor,
  sunrise recovery, night endurance, joint strength and installed RF/GNSS tests
  remain explicit pilot acceptance work.

Do not mark the goal complete from this progress file.
