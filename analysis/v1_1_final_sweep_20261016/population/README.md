# Final parts, population, RF and power sweep

The current parts population and supplier placements have no new order-blocking identity, value, package, pin-map or orientation mismatch in this sweep. The Y25 package remains a three-assembly pilot with **57 fitted references, 30 MPN/LCSC groups, 41 top and 16 bottom placements**. **U6 alone is omitted from automatic assembly; C14, C23 and R27 remain fitted.** U8 must retain **supplier CPL 90°**, despite its native KiCad 180° angle.

This conclusion permits review of the existing pilot design. It does not qualify solar input limits, cold operation, antenna performance, or physical assembly. Supplier factory CAM and the physical checks below remain separate requirements.

## Exact sources and independent reconciliation

- Frozen review checkout: commit `a146a17`, PCB `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`, schematic `c772c2a0edff4d6f7616afb0988fc95c2cbb8c2d3572c1429fc0f3718f69e921`.
- Live board after root restored its missing VSTOR segment: `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13`. Full live/frozen PCB, schematic, project and rule hashes are in [audit.json](audit.json).
- Supplier package: [v1.1-pilot-supplier-20261016](../../../hardware/gerbers/v1.1-pilot-supplier-20261016/README.md), manifest `58f6b271612645eee0a7e32a996dce4e63b2fe7ef8eb292749b16f16228b7e86`, CPL `bf3bb3cf5d633fe95922b7a415dff4278c8bb8fd261d1d737c2401d201be1b00`.

[audit.py](audit.py) independently reconciles every fitted reference across a fresh live schematic netlist, live native PCB, frozen package netlist, BOM, CPL and the captured selected supplier rows. MPN, LCSC code, footprint, electrical value and side agree. All 68 footprint poses/identity fields, 259 physical pad records, 882 track/via/arc records, saved GND/SOLAR fill polygons and board copper graphics match the frozen native extraction. This snapshot comparison does not replace the separate full-copper connectivity check. The initial live snapshot had one missing VSTOR segment; root restored it before this final comparison. No CAD was edited by this sweep.

The supplied verifier also passes on the frozen checkout: 45 source hashes, 47 evidence hashes, 37 package output hashes, and all 57 selected supplier rows. The full [selected-parts.csv](selected-parts.csv) groups every fitted part by exact MPN and includes its actual schematic value and supplier-listed specification. Supplier summary descriptions are preserved as evidence, not treated as manufacturer guarantees.

Manual/mechanical exclusions are AE1, AE2, C5, H1, H2, J1, J2, J3, J4 and J20. In particular, C5 is absent from the reflow BOM/CPL. Its pad 1 is VBAT, pad 2 GND and pad 3 SC_MID. Antenna wire and solar parts are hand-fitted. The pilot stencil removes only the 16 U6 apertures; support circuit parts are not silently dropped.

## Parts and orientation findings

| Parts | Actual selection and electrical check | Result or limit |
|---|---|---|
| U1 | BQ25570RGRR, VQFN-20 plus exposed GND. Current VIN, VSTOR, VBAT, buck/boost and feedback pin nets agree with the retained circuit. | Bottom CPL 270°. Separate input-voltage and input-power limits remain important. |
| U2 | RAK3172-8-SM-NI, C5452091; 3.3 V supply, standard SWD and UART mapping retained. | Top CPL 90°, lower-left index and twelve-pad lower edge in preview. This exact regional RF module is not proof of 433 MHz reception. |
| U3 | MAX-M10S-00B; VCC/V_IO/V_BCKP share the filtered rail. | Top CPL 180°, lower-right index. Rail screen stays below 3.6 V; startup/filter impedance still needs measurement. |
| U4 | MS561101BA03-50, existing 3 × 5 mm eight-pad package and I²C configuration. | Top CPL 270°. The pressure port is not the pin-1 indicator. |
| U5 | TMP117AIYBGR, correct six-ball YBG map: A1 SDA, A2 SCL, B1 V+, B2 GND, C1 ADD0, C2 ALERT. The two latter balls remain grounded. | Top CPL 180°, lower-right A1. The fitted identity is the AI grade, not the earlier N-grade label. |
| U7 | LIS2DH12TR, 2 × 2 mm LGA-12; supply, I²C and interrupt nets retained. | Top CPL 0°, lower-left index. Existing 81% land-area paste apertures retained. |
| U8 | TLV8801DBVT, SOT-23-5; output and negative input share SC_BAL_OUT before R26. Supply is VBAT. | **Top CPL 90°**, vertical body, three leads right and pin 1 lower-right in the corrected preview. |
| D1/D3 | Leiditech PESD5V0U1BB, C5272735; bidirectional 5 V TVS, nominal 0.5 pF, existing SOD-523 lands. | Electrical polarity does not matter, but the long body axis does. Supplier placeholders do not independently certify the real body fit; factory review remains required. |
| L1 | Coilcraft LPS4018-223MRC, 22 µH. TI explicitly lists the LPS4018-223M family for its boost stage. | Existing package and terminal nets retained. No substitution inferred from the model name. |
| L2 | PROD Technology PWCWAQ1608F-100KTT, 10 µH ±10%, maximum DCR 2.405 Ω; **typical** Isat/Irms both 280 mA at 25°C. | Passes the conditional peak-current screen below. Preview is a placeholder; actual body/lands need factory acceptance. |
| FB1 | BLM15AG601SN1D, 600 Ω at 100 MHz, maximum initial DCR 0.52 Ω. | DCR does not guarantee u-blox's ≤0.2 Ω supply-path recommendation. This is a retained qualification issue, not proof of failed reception. |
| C1, C4/C7/C9–C12/C14/C15/C17/C19/C20/C22/C23 | C1 is 10 nF C0G/25 V; the thirteen 100 nF parts are CL05B104KO5NNNC, 16 V X7R, 0402. | Values/packages match the schematic and selected supplier rows; all are nonpolar ceramics. |
| C2/C3/C16, C6, C8/C21 | Respectively 4.7 µF 10 V X5R/0603, 22 µF 25 V X5R/0805, and 10 µF 10 V X5R/0603. | Keep these parts. Bias loss and startup performance are the relevant limitations; nominal capacitance alone is insufficient. |
| R1–R27 present in the BOM | All 25 fitted resistor references match the schematic and exact supplier selections, including zero-ohm links. R1 is 7.50 MΩ, R24/R25 4.75 MΩ, R26 22 Ω. | R27 remains the exact 3.3 MΩ ±0.1%, ±25 ppm/K 0805 part MCU0805MD3304BP500, not a generic ±100 ppm/K replacement. |

All seven populated IC closeups were visually reread against the current numbered pad maps. Observations agree with the [supplier placement review](../../v1_1_supplier_review_20261016/final-placement-review.md); they are preview checks, not inspection of manufactured joints. The corrected U8 import changed no other placement row.

Primary pin/package sources are the retained [TMP117 datasheet](../../v1_1_peer_review_20261014/digital/sources/tmp117.txt), [MAX-M10S datasheet](../../v1_1_peer_review_20261014/digital/sources/max_m10s.txt), [RAK3172 manufacturer documentation](../../v1_1_peer_review_20261014/sources/rak3172-datasheet.txt), and [identity source record](../../v1_1_release_20261012/identities/README.md). Current values, not historical placement coordinates, control this sweep.

## L2 current and loss screen

The newly inspected [PROD manufacturer source](l2-manufacturer-source.md) specifies its 280 mA current numbers as **typical**, with electrical ratings at 25°C. It supplies no guaranteed minimum saturation current over temperature and no inductance-drop criterion in the retrieved one-page table. The LCSC summary omits that distinction.

TI BQ25570 §8.1.3.2 calls for a buck inductor with peak capability above 200 mA. Section 8.1.3 recommends another 25% margin where load transients are expected. Its §6.6 current-limit table gives 205 mA maximum under the stated conditions; 1.25 × 205 = **256.25 mA**, below 280 mA by **23.75 mA**. This is a useful nominal-design screen, not a guaranteed worst-case margin: the inductor rating is typical, and TI's stated VOUT interval is below 3.3 V while this circuit's nominal set point is 3.3116 V.

Maximum stated DCR is relatively high. At an illustrative 100 mA DC, I²R is **24.05 mW**. That calculation excludes ripple, switching, temperature rise and duty cycle. Retain the proven part for these pilots, measure startup/load behavior and temperature, and do not describe it as lossless or cold-qualified. No evidence here requires changing its footprint or replacing it before prototype assembly. [TI primary document ledger](../../v1_1_release_20261012/power/source-manifest.json).

## Power and RF limits retained for qualification

[power_screens.py](power_screens.py) recomputes the existing tolerance method from the actual live resistor values, rather than from an obsolete BOM. [Results](power-screens.json): charge ceiling **5.0407 V nominal**, **4.8373–5.2519 V** in the independent ±1%/±100 ppm/K/65 K screen; buck output **3.3116 V nominal**, **3.1785–3.4497 V**. The screen includes ±2% set-point error but does not inherit a datasheet guarantee conditioned on 0.1% resistors.

The active balancer matches CAP-XX's published follower-plus-isolation-resistor topology. The divider is scaled to 4.75 MΩ per side, with feedback before 22 Ω and 100 nF local bypass. The screened high cell is **2.6738 V**, below 2.75 V; an initial 52% split before correction reaches **2.7310 V** and leaves only 19 mV for unmodeled effects. The 4.5 mV op-amp offset used here is a 25°C limit. Operation below the 1.7 V minimum supply, common-mode margin near startup, output current, cold leakage, ripple and F-scale-load stability must be measured. These numbers are not a transient or electrochemical simulation. See the [CAP-XX/TI source ledger](../../v1_1_release_20261012/power/source-manifest.json).

Direct solar input remains the largest unclosed operating-envelope issue. Two parallel 4.8 V/50 mA nameplates imply **0.48 W**, compared with TI's **0.40 W recommended input** and **0.510 W absolute peak**. The nameplate does not establish actual available power or cold Voc. TI specifies **5.1 V recommended VIN and 5.5 V absolute maximum**; 80% MPPT does not clamp the voltage during open-circuit sampling. The actual source, full-storage and cold-start waveform must be characterized before claiming this assembly is safe across the flight envelope. This is a retained hardware limitation, not a newly discovered BOM mismatch or proof that every flown board exceeded a limit. [Panel source](../../v1_1_solar_attachments_20261012/sources/zachtek-panel.txt), [power source ledger](../../v1_1_release_20261012/power/source-manifest.json).

Samsung's exact-family reference curves give approximately 4.43 µF for each C8/C21 at 3.3 V, 13.86 µF for C6 at 3.3 V, 1.69 µF for C2 at an illustrative 4 V, and 1.31 µF for C3 near 5.04 V. They are typical curves, not guaranteed simultaneous bias/temperature minima. Keep the radio's 10 µF plus 100 nF bypass and the upper bulk part. Measure VIN, VSTOR and local U2/U3 rails during weak sunlight, GNSS startup and TX. [Manufacturer curves and limits](../../v1_1_peer_review_20261014/power/README.md).

The unchanged RF geometry retains the rear ground under U3.11 and the feed, the C5 1.30 mm displacement, and the repaired ground stitches. The GNSS feed remains **5.023 mm from boost and 2.625 mm from buck switch copper** in projection. Switch connections use filled polygons, not only tracks. The converter return still needs a wider board region to connect all its grounds, so a connectivity pass is not a low-inductance return proof. The **0.75 mm RF line remains unqualified as 50 Ω**. The prior ideal model's roughly 36.8 Ω screen excludes actual pad/diode transitions, finite ground, mask and manufacturing tolerance. Ground continuity is necessary but does not establish reception. [Exact frozen RF/copper analysis](../../v1_1_engineer_review_20261015/rf-power/README.md).

C5 remains the on-hand 1 F flat DMF part, rated −40 to +70°C and 5.5 V stack. Fit after reflow and cleaning using its prescribed secondary soldering process. Neither altitude nor the thin package extends that temperature rating. Measure individual cell voltage, actual board temperature, source input and loaded rails on the pilots before treating the revision as flight-qualified. [CAP-XX datasheet](../../redesign_20261010/energy/sources/capxx_dmf_v1_9.txt).

## Reproduce this sweep

Run KiCad's bundled Python for `analysis/v1_1_top_gnss_20261014/power/snapshot.py`, targeting `hardware/pcb/stratolink.kicad_pcb` and this directory's `live-native.json`. Export a fresh KiCad XML netlist of the live schematic to `live-netlist.xml`. Then run:

```sh
python3 analysis/v1_1_final_sweep_20261016/population/audit.py --frozen /path/to/review-checkout
python3 analysis/v1_1_final_sweep_20261016/population/power_screens.py
python3 /path/to/review-checkout/analysis/v1_1_supplier_review_20261016/verify.py
```

The scripts write analysis files only. They do not change CAD, refill zones, alter selected parts, or submit an order. Primary documents, source hashes, outputs and screenshot identities are bound in `source-identities.json`.
