# Part identities, libraries and U7 assembly routing

2026-10-12. These isolated candidates start from `59979799c5809d636639084227d9fee75c8de1d9`. Canonical hardware was not edited by this workstream. Root integration and the other agents' header/power changes require a fresh combined review.

The metadata candidate reconciles the actual assembled orderables and preserves all copper. The separate U7 candidate replaces the central underside traces with perimeter escapes and bottom-layer connections, adds two outside-body vias, and reduces U7 stencil aperture area to 81%. All 232 physical-pad connected sets remain identical. These checks establish CAD consistency; assembly yield and sensor stress still require the pilot build.

## Frozen candidates and evidence

- Metadata: `/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/identities/metadata-candidate`. PCB SHA-256 `4d2e92f11d8f9164dfe0600c1dd1b72469ce6cc4fcc4ab0568df5c3312abf041`; schematic `e16bd82c79bea406fafd13f703a83d77b27d1c4cfa3540e3804959c8124ff1f9`.
- U7, based on that metadata: `/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/identities/u7-candidate`. PCB SHA-256 `c9e744b3144553e929bc3f3ba12b6bc3c272e6904ad25db113fd604e9b9cce6c`; schematic unchanged. [Final file hashes](u7-frozen-manifest.json), [exact object UUID scope and connectivity](u7-verification.json).
- [Metadata verification and full file manifest](metadata-verification.json), [complete per-reference fields and library names](metadata-build.json), [independently exported baseline netlist](baseline-netlist.xml), [candidate netlist](candidate-netlist.xml).
- [Native geometry before/after](u7-before-after.png), [measured copper and C6 gaps](u7-geometry-screen.json), [native extracted geometry](u7-geometry-native.json).
- [Uniform 0.10 mm process screen](candidate-u7-screen-0.1.json): four existing bare-board silk advisories, no electrical, parity or library findings. [Uniform 0.15 mm screen](candidate-u7-screen-0.15.json): 21 findings versus 19 baseline; the two added records describe the same SCL/U6-pad-6 gap. [Scoped 0.15 mm screen](candidate-u7-scoped-0.15.json): exactly the baseline 19 signatures; [negative-control proof](u7-scoped-rule-proof.json).

## Identity decisions

The release fields use the actual shipped selection captured from JLC in [previous-selected-parts.txt](../jlc/previous-selected-parts.txt), rather than the stale BOM database or generic schematic comments. This verifies selected identity, not current stock for every item. The generated [full identity table](bom-identity-audit.csv) lists each reference and supplier code.

| References | Finding and correction |
|---|---|
| D1, D3 | Comment/value `ESD9B3.3ST5G` did not identify the fitted selection. Both are `PESD5V0U1BB`, LCSC `C5272735`, a bidirectional 5 V SOD-523 TVS. Keep the existing SOD-523 lands, orientation and RF routing. New local symbol identity uses the existing bidirectional two-terminal representation. |
| U5 | The flown selection was `TMP117AIYBGR`, `C2871893`; prior `TMP117NAIYBGR` metadata was inaccurate. Use the available AI grade selected by the release lead, with the corrected YBG ball map unchanged. AI and N share this package/pin map; they are not interchangeable accuracy labels. |
| C5 | Placed terminal mapping is pad 1 positive, pad 2 negative, pad 3 center balance. The old reusable footprint exchanged center/outer numbering; refreshing it blindly would be wrong. The back/component-view drawing has negative left and positive right, consistent with the mirrored placed view. Copy the proven placed mapping into a release library. Balance is still NC in this metadata-only candidate; the independent power candidate supersedes that state and its assembly note. |
| U6 | The schematic footprint identifier disagreed with the placed `SMD6_LTR-390UV-01_LTO-L`. Both now point to the board-specific release copy. No pad movement or optical claim changes. |
| U1 | Five thermal holes were numbered 22–26, but they are physical connections to exposed GND pad 21, not extra IC pins. Renumber them 21 without changing UUIDs, holes, lands or GND. Symbol/PCB parity now agrees. |
| U1/U2/U4/U6/U7 | Normalize descriptions and exact orderable fields consistently between schematic and PCB. U2/U7 had duplicate case/alias descriptions; updating only `Description` left parity errors, so those aliases are reconciled too. |
| C1, L2, R4, R5, R3/R7 | Use the actual selections `GRM1555C1E103JE01D C3855387`, `PWCWAQ1608F-100KTT C436784`, `0402WGF3654TCE C2766827`, `GR0402F4M42TAG00 C49654874`, `FRC0402F4754TS C2998153`. Preserve placed package geometry and electrical values. |
| Remaining populated R/C/L/FB/IC references | Set explicit supplier/manufacturer-part fields from the captured order, preserving electrical values and pins. Replace misleading inherited resistor descriptions/datasheet links. Manufacturer names not independently established for R3/R5/R7 remain unspecified rather than guessed. |
| J3/J4 | Left untouched here; the header workstream owns their values, geometry and release footprint identities. |

The [Leiditech-authored PESD5V0U1BB datasheet](https://uploadcdn.oneyac.com/attachments/files/brand_pdf/leiditech/3D/92/PESD5V0U1BB.pdf) specifies bidirectional protection, 5 V reverse standoff, 6 V minimum breakdown and nominal 0.5 pF capacitance. This supports the low-capacitance RF selection; the source is the manufacturer's datasheet mirrored by a distributor.

The [TI TMP117 datasheet](https://www.ti.com/lit/ds/symlink/tmp117.pdf) gives the standard TMP117 maximum errors as ±0.1 °C at −20…50 °C, ±0.15 °C at −40…70 °C, ±0.2 °C at −40…100 °C, ±0.25 °C at −55…125 °C and ±0.3 °C at −55…150 °C under TI's averaging/conversion test conditions. It does not promise ±0.1 °C across the flight environment or ambient-air measurement accuracy. The local source used is `analysis/v1_1_layout_20261012/pcb_audit/sources/tmp117.pdf`. U5 remains A1 SDA, A2 SCL, B1 VCC, B2 GND, C1 address GND, C2 unused ALERT grounded.

The C5 polarity comparison uses the cached [CAP-XX DMF datasheet](../../redesign_20261010/energy/sources/capxx_dmf_v1_9.pdf), page 2, including its explicit back view. U1's exposed-ground-pad identity follows the [TI BQ25570 datasheet](https://www.ti.com/lit/ds/symlink/bq25570.pdf).

## Why the library mismatches disappeared

The baseline had 51 library mismatches and 11 parity records, including U1's extra pad numbers. Fifty-two explicitly named `Stratolink_v1p1_<ref>_<footprint>` copies preserve each placed footprint, including the already reviewed local land, mask, courtyard, mounting and keepout decisions; U7 is copied explicitly even though it did not contribute an original mismatch. Old reusable libraries remain untouched. This makes future library refresh controlled, instead of replacing deliberate board geometry with a stock/imported version.

KiCad's native `FootprintSave` normalizes most objects but initially left embedded rule-area outlines in board coordinates for U3/U4/J20. Moving those in-memory footprints to the library origin before exporting corrected the three remaining mismatches; that transformed board is never saved. Native footprint comparison and full DRC verify the final copies. No geometry change was used to hide a mismatch.

## U7 conformity change

[ST TN0018 Rev 8](https://www.st.com/resource/en/technical_note/tn0018-handling-mounting-and-soldering-guidelines-for-mems-devices-stmicroelectronics.pdf) §3.2–3.3 recommends no top metal/routing/vias beneath the MEMS body outside the contact lands, 70–90% stencil aperture area and 90–150 µm stainless stencil thickness. Its layout guidance favors trace-fed ground lands over unequal direct plane attachment and permits bottom-layer routing. The [LIS2DH12 datasheet](https://www.st.com/resource/en/datasheet/lis2dh12.pdf) gives a 2.00 ±0.15 mm body and the pin functions used in the independent net check.

The previous center contained approximately 0.508 mm² of top copper traces. It now contains zero in the measured central keepout. All twelve copper lands retain their previous dimensions, position and rounded corners, including the small existing pad-5 offset. Each GND lead now has its intended trace connection; new zone-connect overrides on pads 3/6 complete the existing overrides on 5/7/8. One keepout reserves the maximum 2.15 mm body against top pour/vias; a second blocks routing in its central area. Only lead escapes enter the peripheral contact region.

The change removes 21 old segments, adds 20, adds two Ø0.50 mm / drill 0.30 mm vias and two keepouts. Copper edits stay within the local U7/U6/C6 area; the reported 2.1×10⁻⁸ mm² outside-window F.Cu difference is polygon-rounding noise. The two vias lie beyond U7's maximum body envelope. The new power via connects to C6 pad 2 on the bottom. Native fill and connectivity confirm the same net at every existing physical pad.

U7's `solder_paste_margin_ratio -0.05` reduces each side by 5% of the dimension, producing 90% linear dimensions and **81% aperture area**, rather than a 5% total reduction. The actual Gerber proof in [review_u7_paste.py](../manufacturing/review_u7_paste.py) independently checks all 12 flashes at their unchanged centers: 0.315 × 0.405 mm apertures with 0.04725 mm corner radius against 0.350 × 0.450 mm copper with 0.0525 mm radius. Area is 0.12565855 mm²; area divided by aperture perimeter and a 100 µm stencil thickness is 0.92472. Do not apply a second global reduction in CAM. These calculations support printability; they do not measure paste transfer or solder-joint reliability.

### Local clearance disposition

The SCL passage below the new power via and above U6's SDA pad 6 measures **0.128 mm** copper clearance. A 0.15 mm gap on both sides cannot fit in the approximately 0.378 mm corridor with a 0.10 mm trace and the retained 0.25 mm copper-to-drilled-hole constraint; 0.400 mm is needed. Moving the via to the right would collide with an existing bottom GND rail and require additional circuit rerouting. Retain the ordinary Ø0.50/0.30 mm via and apply the [specific 0.12 mm rule](u7-clearance-rule.kicad_dru) only to F.Cu SCL tracks versus U6 pad 6. Its threshold remains above the reviewed JLC 0.10 mm process floor. There is no blanket waiver. An intentional 0.13 mm test rule produces exactly the two expected 0.128 mm failures; the final 0.12 mm rule returns exactly the baseline stricter-screen signatures.

The power-via annulus is **0.137504 mm** from the rounded C6 positive land (0.131 mm using its bounding rectangle). Its drilled hole is **0.237504 mm** from that land (0.231 mm conservative rectangle). The annulus and pad are both +3.3 V and deliberately joined by the new B.Cu trace; a different-net electrical-clearance rule does not apply. C6 has no local clearance override. The hole is outside the paste land. Because this board is bare, inspect solder wicking at this trace/via on the pilot; do not confuse absent different-net DRC with a solder-process measurement.

### Remaining bounded assembly evidence

The ST-specific [STEVAL-MKI151V1 manufacturing archive](https://www.st.com/resource/en/board_manufacturing_specification/steval-mki151v1_gerber.zip) was identified on ST's product CAD page, but the download repeatedly failed or timed out during this review. **No claim is made that the retained imported lands exactly equal that evaluation board's copper pattern.** The provided fix uses TN0018's explicit routing/stencil guidance and preserves the flown lands. Exact reference-pattern comparison and assembler CAM review remain separate from the verified CAD corrections. Pilot solder joints, accelerometer offsets/noise and temperature/handling effects must be measured.

## Reproduction and integration

Run the builders only to recreate a new scratch candidate; they replace their named scratch directories. Frozen manifests are the review contract. KiCad is 10.0.0, with its bundled Python 3.9 and native pcbnew; analysis Python provides Shapely/matplotlib.

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/identities/build_u7.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/identities/freeze_u7.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/identities/verify_u7.py
analysis/.venv/bin/python analysis/v1_1_release_20261012/identities/screen_u7.py
analysis/.venv/bin/python analysis/v1_1_release_20261012/identities/screen_u7_scoped.py
analysis/.venv/bin/python analysis/v1_1_release_20261012/identities/plot_u7.py
```

Merge the U7 object delta relative to the metadata candidate, its one library footprint and its exact rule. Preserve independently changed J3/J4 and C5/balance metadata. **Remove stale zone `filled_polygon` / `filled_areas_thickness` caches before loading and refilling the merged board.** Loading a newly inserted via against stale copper can assign it the old pour's GND net before refill; verify new via net assignments and every connected pad after the fresh load. Re-export manufacturing layers from the final combined candidate, and repeat DRC/parity plus the paste audit.

## Independent balancer review

**Final combined review passed** on PCB `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15` and schematic `044984037a7346adc92ee9ea142e6c285ee7f6b66efc87e0a1ad195495379cc9`. The [integrated native report](balance-integrated-native-review.json) confirms zero opens, all 232 old pad islands and all old F.Cu/B.Cu pad shapes/drills preserved, including the enlarged headers, plus the 13 correctly connected new pads. Its [fresh netlist](balance-integrated-netlist.xml) independently confirms polarity, values and feedback placement.

The [full-board geometry audit](balance-integrated-geometry-review.json) confirms all 996 retained conductors unchanged apart from the VBAT net rename; the exact 28 removed and 353 added conductors match the frozen author's declared delta. Four board zones retain their outlines/settings and all 32 board drawing/outline objects remain exact. The 13 new pad geometries/nets are unchanged; only schematic pin-function/type metadata was added during integration. All 66 component/model registrations match the measured source, and all 23 local model files match by SHA-256. The physical findings below therefore apply to this final combined candidate. These independent checks do not replace the final native DRC/ERC and manufacturing-layer review recorded by their respective workstreams or physical pilot qualification.

**The frozen isolated candidate passes the independent circuit, retained-pad and nominal assembly checks.** PCB SHA-256 is `3bf0023e309336249e90deb1f52270f4108e61e40b558b4ec56a1df768ae1d4c`; schematic is `7bd031d5b4a2ffcc22f4e8a04f664771204c4796c048ee348f0a95bebc1ef024`, at `/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/power/balancer-reviewed`. The five-part placement is U8 (55.65, 36.1), R24 (57.4, 33.9), R25 (58.65, 34.9), C22 (55.6, 38.3) and R26 (61.2, 42.5), all on the rear. Earlier exploratory placements are superseded. [Measured model envelopes](balance-placement-model-review.json) and [projection](balance-placement-model-review.png) use new sequential native exports from that frozen board. Combined release checks and physical pilot qualification remain separate.

Native KiCad STEP exports were independently imported into OCCT, checked as valid solids and measured against C5, neighboring packages and each other. KiCad GLB preserves the solar panel and wire models that STEP omits. Its primitive bounding boxes provide conservative separation lower bounds. The smallest new-part/C5 gap is R26 at 2.707 mm; U8 to C22 is 0.5325 mm; R26 to the opposite-face U3 model is 0.6324 mm. The suspension-hole-to-model XY lower bound is 1.2703 mm. The modeled solar assembly stays at least 12.0136 mm away, and its positive wire at least 35.7863 mm away. These are nominal CAD measurements, not physical tolerance or strength qualification; solar wire shape and film assumptions remain as recorded by the mounting workstream. CAP-XX's body tolerance and TI's package tolerances must be allowed in the pilot fit.

The source circuit is CAP-XX's active-balancing Figure 7, with TI's TLV8801 DBV pin map independently checked. U8 output pin 1 and inverting pin 4 join on `SC_BAL_OUT` **before** the 22 Ω R26. R26's other terminal joins C5's physical center pin 3. U8 pin 3 receives the equal-resistor half-voltage reference; pin 5 is VBAT and pin 2 GND. The new schematic symbol retains C5 outer pin 1 positive and pin 2 negative. The [independent native result](balance-native-review.json) and [fresh schematic netlist](balance-native-netlist.xml) confirm these connections and selected values. All 232 retained physical-pad connected sets match the integrated U7 baseline, including R22.1's rerouted VSTOR sense connection. There are 13 new pads and zero unconnected items after native refill. Every existing F.Cu/B.Cu pad polygon, drill and position matches the author's original baseline.

The isolated candidate retains the old header geometry; it must be merged into the reviewed elongated-header project without replacing that geometry. Its two declared D3.1/J4.1 GND thermal overrides are 0.25 mm gap and 0.25 mm bridge, recorded by exact pad UUID in the [author manifest](../power/thermal-author-manifest.json). Apply the matching local-footprint properties and rerun combined native DRC. The pad/island proof does not independently waive that integration step.

CAP-XX's room-temperature example and this pin-map check do not establish closed-loop behavior with this supercapacitor across the flight environment. Pilot validation must measure startup, midpoint balance and oscillation/ringing under the real capacitor, temperature and solar supply conditions. Source artifact URLs and hashes are recorded in the [power source manifest](../power/source-manifest.json).

The model reproduction uses `kicad-cli pcb export step --component-filter REF` with the board retained, then excludes its solid during OCCT measurement. Export STEP files sequentially: KiCad's shared temporary filename can collide when several exports use one directory concurrently. Export J1/J2 as GLB to preserve their VRML solar/wire assemblies. `review_balance_models.py` records all exported hashes, valid-solid counts and distances. Run `review_balance_native.py` with the frozen candidate, `integrated-u7-r2` as connectivity baseline and `identities/baseline` as `--geometry-baseline` for the authored header geometry.
