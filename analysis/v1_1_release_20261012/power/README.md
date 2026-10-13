# v1.1 power and storage adversarial audit

Audit baseline: `59979799c5809d636639084227d9fee75c8de1d9`; PCB SHA-256 `ea78337c91c73d27b813f09f74dd2d2993e5a82d09800362d82c49a0c4f3ed96`. This directory records calculations and a proposed minimum repair. It does not authorize an order or certify flight operation. No canonical CAD or firmware was changed by this audit.

## Decisions supported by this audit

1. Retain the on-hand flat **DMF4B5R5G105M3DTA0** capacitor and its mounting envelope. A different package is unnecessary for the pilot.
2. Change **R1 from 8.25 MΩ to 7.50 MΩ** for the selected active-balanced pilot, retaining R2 = 4.22 MΩ. The preferred lower 7.32 MΩ setting remains a documented alternative, but currently listed 0402 stock is insufficient for a practical assembly order. The original charge setting has a valid tolerance corner above the capacitor's 5.5 V rating even at room temperature. This is a tolerance failure, not a claim that every existing board overcharges.
3. Add the **CAP-XX application circuit using TLV8801, two 4.75 MΩ resistors, a 22 Ω output isolation resistor and a 100 nF local bypass**, with access to the capacitor's actual centre terminal. A reduced total voltage alone does not control leakage-driven cell imbalance over time. The isolated candidate is a pilot design, requiring the specific startup/oscillation checks below before flight qualification.
4. Keep the **solar input protection decision open** while evaluating a source-limited front end. TPS709 is a plausible experiment, but its dropout, startup, lightly loaded regulation and interaction with the harvester prevent treating it as a drop-in protective part. The existing direct panel connection is not substantiated against BQ25570 voltage and input-power ratings.
5. Correct the firmware's computed `VBAT_OK` metadata. Boot voltage is not its switching threshold on this board.

These are independent issues. Balancing does not fix the charge ceiling, and an input voltage limiter does not automatically limit input power.

## Actual circuit and v1 comparison

`actual-netmap.json` preserves all 61 placed footprints and their actual pad nets. `v1-topology-comparison.json` compares 48 power/peripheral references against working v1 commit `9bdd19ec707455271f48f5a5d8be352fc696cf9c`: the selected values and physical pad nets match. Deliberately removed microphone pins and the repaired temperature sensor are excluded explicitly. No newly introduced power connection failure was found.

U1 is BQ25570. `VIN_DC` receives the two parallel panels on `+SOLAR`; `VOC_SAMP` is tied to VSTOR, selecting 80% Voc sampling. `EN#` is grounded. **`VOUT_EN` is tied directly to VSTOR**, so buck enable does not wait for `VBAT_OK`. `VBAT_OK` reaches MCU PB5 through R8 = 100 kΩ. U1's NC pins may be grounded per TI. L1 is 22 µH and L2 is 10 µH.

C5's placed positive outer pad 1 is VBAT; outer pad 2 is GND; physical centre pad 3 is unconnected. Its reusable library numbering is a separate release-library issue: do not swap the already working outer power connections. The existing schematic exposes two terminals; adding the balancer requires a correct three-terminal local symbol.

The MAX-M10S VCC, V_IO and V_BCKP are tied together behind FB1 on 3.3 V; VIO_SEL is open. Reset cannot remove its power. The MAX-M10S permits 3.6 V maximum on these supply inputs and requires at least 2.7 V on V_IO in this configuration. [u-blox datasheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf)

## Charge ceiling and resistor choice

The actual divider is `VRDIV — R1 — VBAT_OV — R2 — GND`. TI's equation is:

`VBAT_OV = 1.5 × 1.21 V × (1 + R1/R2)`.

The reproducible `calculate_limits.py` includes independent ±1% resistors and ±2% set-point error using TI's EVM screening method. The cold screen additionally assumes independent ±100 ppm/K resistor drift over 65 K from 25°C to −40°C. Actual purchased resistor TCR must satisfy that assumption. The EVM method excludes ripple and is not a substitute for the datasheet guarantee conditioned on 0.1% programming resistors. [TI EVM guide, p.7](https://www.ti.com/lit/pdf/SLUUAA7), [TI BQ25570, equations and electrical characteristics](https://www.ti.com/lit/gpn/BQ25570)

| R1 | Nominal charge ceiling | Cold-screen maximum | Initial high cell at 52% of stack | Interpretation |
|---|---:|---:|---:|---|
| 8.25 MΩ, existing | 5.3633 V | 5.5920 V | 2.9078 V | Fails total and initial-cell screen |
| 7.87 MΩ | 5.1998 V | 5.4197 V | 2.8182 V | Total fits; initial cell does not |
| 7.68 MΩ | 5.1181 V | 5.3335 V | 2.7734 V | Initial cell still above 2.75 V |
| 7.50 MΩ | 5.0407 V | 5.2519 V | 2.7310 V | Only 19 mV initial-cell margin |
| **7.32 MΩ** | **4.9633 V** | **5.1703 V** | **2.6886 V** | **61.4 mV initial-cell margin** |

The original **room-temperature** screen already reaches **5.5437 V**, exceeding 5.5 V before adding the TCR scenario. Thus its failure does not depend on the cold-drift assumption. The 7.32 MΩ divider totals 11.54 MΩ, within TI's 11–15 MΩ recommendation. A candidate is **CRCW04027M32FKED**, subject to stock, tolerance and TCR verification; the CAD prototype must not inherit the old 8.25 MΩ supplier ID. R2 remains CRCW04024M22FKED in the historical selected-parts list.

The 52% calculation reflects CAP-XX's initial matching example; it is not a bound on long-term leakage imbalance. The manufacturer recommends balancing its series-cell modules even below rated total voltage. [CAP-XX balancing whitepaper](https://cap-xx-assets.s3.eu-west-2.amazonaws.com/cap_xx_whitepaper_supercapacitor_cell_balancing_d39dd4559f.pdf)

## Selected practical pilot and minimum active balancing circuit

The sourced pilot uses **R1 FRC0402F7504TS / C3013187, 7.50 MΩ**, with a 5.0407 V nominal and 5.2519 V screened maximum charge ceiling. Active balancing gives a screened high cell of **2.6738 V**, leaving **76.2 mV**. Before correction, a 52% split is **2.7310 V**, only **19.0 mV** below the cell rating; ripple and cold startup remain mandatory pilot checks. This is an explicit reduction in margin compared with 7.32 MΩ, accepted for the sourced pilot, not an equivalent bound.

At the same illustrative 2.51 V discharge endpoint and nominal 1 F, reducing the charge ceiling changes usable stored energy from **11.23 J to 9.55 J**, approximately **15% lower**. This compares capacitor energy, not night endurance.

The divider pair is **FRC0402F4754TS / C2998153**, 4.75 MΩ, ±1%, ±100 ppm/°C. Scaling both resistors preserves the ratio and voltage-error calculation while increasing divider current. At the selected 5.2519 V upper screen the divider draws **0.5620 µA**, giving about **1.012 µA typical** IC-plus-divider idle current before actual balancing current. The 10 MΩ examples below preserve the manufacturer's published circuit and comparison calculation; the candidate uses 4.75 MΩ. U8 is **TLV8801DBVT / C544879**; R26 is **0402WGF220JTCE / C25092**; C22 is **CL05B104KO5NNNC / C1525**. Parent sourcing evidence is under the release `jlc/` directory.

`balancer-final-candidate.json` is the frozen routed source manifest; `thermal-author-manifest.json` is the narrow existing-pad override contract for integration. `balancer-candidate.json` records the earlier unrouted builder stage and must not be used as the fabrication source.

The final five parts occupy the upper-left rear, clear of the retained flat capacitor. Existing component placements and original pad copper/drill geometry are unchanged. The exact authored changes are the R1 metadata/value, C5's third terminal/net and symbol, the new circuit, and two local ground-pad thermal dimensions. D3.1 and J4.1 change from inherited 0.5 mm gap/bridge to local **0.25 mm gap/bridge**; connection style and the minimum two-spoke requirement remain unchanged. The final enlarged J4 header land is part of the independent header integration, so the baseline-sized J4 in this power-only source is not the release land.

The new supply trace is **9.32 mm**, and the midpoint connection is **22.14 mm**, each with two 0.5/0.3 mm vias. At 0.15 mm width and nominal 35 µm copper, their calculated 20°C conductor resistances are approximately **0.031 Ω** and **0.073 Ω**, excluding vias and manufacturing variation. These are calculations, not measurements; the midpoint conductor remains small compared with the 22 Ω isolation resistor. Feedback is a local **3.11 mm** connection before that resistor, and the half-stack reference routes remain local. All new traces are 0.15 mm.

Routing the added circuit required replacing the existing **VSTOR ADC sense branch** into R22.1. Removing the original barrier was first checked to isolate only that pad; the power trunk remained connected. The final replacement reaches J4.2 through 28.83 mm and four vias. `adc-stub-removal.json` lists the 27 superseded original routing objects. One original redundant GND stitch at (58.322, 49.346) is also removed because the new routing displaced its rear ground pour; it had no attached trace and otherwise became a dangling via. `balancer-final-candidate.json` identifies all 28 removed and 353 added segment/via UUIDs and proves surviving traces, original pad geometry, and unrelated board objects unchanged. Native physical-pad connectivity is reviewed independently; matching net labels alone is not the proof.

The authored source was frozen at PCB SHA-256 `3bf0023e309336249e90deb1f52270f4108e61e40b558b4ec56a1df768ae1d4c`. Native DRC after a fresh refill has zero opens. A diagnostic using the actual integrated J4 land and the enabled integration PRO/DRU has no thermal, dangling, hole, edge, or courtyard finding, and no clearance finding involving a new power object. Its sole copper clearance is the enlarged J4.4 against the baseline RX segment, which is replaced by the separate header-routing integration. The diagnostic retains expected baseline library and bare-board silkscreen findings. Final integrated DRC and independent circuit/assembly review remain separate release checks; this diagnostic is not a claim that the standalone power-only source is manufacturing-ready.

The subsequent **integrated release check passed** at PCB SHA-256 `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15` and schematic `044984037a7346adc92ee9ea142e6c285ee7f6b66efc87e0a1ad195495379cc9`. `integrated-power-review.json` records a fresh native refill and schematic netlist comparison: all 232 prior pads retain their physical connected sets and all-layer copper/drill geometry, all 13 added pads connect as intended, and there are zero opens. The integrated circuit contains exactly the authored 28 removals and 353 additions; no other route is changed during the power merge. The enabled final DRC has only four known bare-board silkscreen warnings, with zero other findings and zero schematic parity findings. This closes the CAD integration checks; it does not replace the physical and environmental pilot measurements below.

Use the manufacturer's Figure 7 topology, powered by **VBAT**, not the switched/system 3.3 V rail:

| Part or TLV8801 DBV pin | Connection |
|---|---|
| Pin 5, V+ | VBAT, capacitor positive outer terminal |
| Pin 2, V− | GND, capacitor negative outer terminal |
| Upper 4.75 MΩ resistor (10 MΩ in source figure) | VBAT to `SC_HALF_REF` |
| Lower 4.75 MΩ resistor (10 MΩ in source figure) | `SC_HALF_REF` to GND |
| Pin 3, +IN | `SC_HALF_REF` |
| Pin 1, OUT, and pin 4, −IN | `SC_BAL_OUT`, direct local feedback |
| 22 Ω resistor | `SC_BAL_OUT` to `SC_MID`, capacitor centre terminal |
| 100 nF ceramic | V+ to V−, next to the IC |

Feedback remains **before** the 22 Ω resistor. The resistor isolates the capacitive load and limits equalization current; moving feedback to the capacitor midpoint changes the stability problem. The published CAP-XX experiment used TLV8801 and this 22 Ω circuit on another two-cell module at 23°C. TI's generic heavy-capacitive-load advice calls for much larger 30–50 kΩ isolation, so stability of this particular F-scale load is a real pilot measurement, not something a matching netlist proves. [CAP-XX Fig.7–8](https://cap-xx-assets.s3.eu-west-2.amazonaws.com/cap_xx_whitepaper_supercapacitor_cell_balancing_d39dd4559f.pdf), [TI TLV8801 §7.4.4](https://www.ti.com/lit/ds/symlink/tlv8801.pdf)

**Supply and startup:** TLV8801 operates from 1.7–5.5 V. The selected 7.50 MΩ R1 stack maximum screen is 5.2519 V, providing 0.2481 V supply headroom. Its common-mode range is ground through V+−0.9 V; the half-stack reference lies inside this range above 1.8 V. TI specifies protection against output reversal. Behaviour below the 1.7 V minimum supply is not specified, but neither cell can reach 2.75 V at those low total voltages. No regulated 3.3 V supply is needed to start balancing. [TI TLV8801](https://www.ti.com/lit/ds/symlink/tlv8801.pdf)

**Lower-OV comparison accuracy screen:** two 10 MΩ 0402 ±1%, ≤100 ppm/K parts give an upper divider fraction of 0.5082495 with independent 65 K drift. At 5.1703 V, adding 4.5 mV offset yields a high-cell estimate of **2.6323 V**, leaving **117.7 mV**. The 4.5 mV offset limit is a 25°C specification at the listed supply/CM test points; its drift is typical, so this is not an all-temperature guaranteed cell bound. Bias current is only typical in the source table. Leakage from dirty PCB surfaces can dominate nanoampere circuitry; clean before installing the supercapacitor.

**Lower-OV comparison initial equalization:** a 52% initial split at the 7.32 MΩ R1 screened maximum differs from half supply by 103.4 mV. Across 22 Ω that requests **4.70 mA**. TI lists 4.7 mA as typical short-circuit current at 3.3 V, not guaranteed linear continuous drive; initial current limiting can therefore occur. Initial cell voltage already passes the reduced-OV screen, giving the balancer time to settle. The capacitor sees a finite, isolated current path rather than an op-amp output strapped directly to its F-scale capacitance.

**Manufacturer 10 MΩ comparison power:** the divider draws at most 0.263 µA in this resistance screen. TLV8801's fresh datasheet says 450 nA typical quiescent current; the 700 nA maximum applies at 25°C, 3.3 V and the stated input condition. Idle IC-plus-divider typical is around **0.713 µA**, before correction current and the capacitor's own leakage. Do not call 700 nA a guaranteed cold/5 V maximum. CAP-XX's separate tested module measured roughly 1.5–1.7 µA total after settling, which is useful supporting evidence but not a prediction for this DMF at altitude.

Two 10 kΩ passive shunts would draw 258.5 µA at the same stack ceiling. With the capacitor's minimum 0.8 F they alone reduce the screened low initial charge to 3.5 V in 1.37 h, before board loads. Larger shunts save current but require a leakage-mismatch bound the DMF datasheet does not provide. `limits.json` quantifies this tradeoff; arbitrary 1 MΩ shunts are not a justified substitute.

## Solar input: real limits and the LDO candidate

BQ25570 allows **5.1 V recommended VIN, 5.5 V absolute maximum**, input power up to **400 mW recommended**, and **510 mW absolute peak**. The boost stage requires at least **400 mV** between the programmed storage ceiling and VIN while charging. Open-circuit sampling still exposes VIN to panel Voc; the 80% MPPT setting does not clamp the input during sampling. At the selected 7.50 MΩ low OV corner, the charging VIN headroom screen is 4.4373 V (the lower-OV 7.32 MΩ alternative gives 4.3639 V). [TI BQ25570](https://www.ti.com/lit/gpn/BQ25570)

The two parallel 4.8 V/50 mA nameplates imply 480 mW at those labelled operating points, exceeding the 400 mW recommendation. The label is not a guaranteed cold Voc or Isc specification. `flight-screen.json` finds **85 of 458** existing telemetry records above 5.1 V, with one reported **5.538 V** near launch; another high-altitude record reports 5.464 V. These ADC records are not calibrated Voc or peak captures and can be biased by old rail assumptions, so they do not prove the silicon experienced absolute maximum violation. They do make it unreasonable to assert that the 4.8 V label establishes safe input voltage.

**TPS70950 is an experiment, not yet a release selection.** It has 2.7–30 V input, a SOT-23-5 option and low no-load ground current (1.4 µA typical / 2.25 µA maximum for the relevant output range). It limits output by series regulation rather than dumping the full panels' power as a shunt at full storage. Important constraints from the exact table:

- A 5 V part's table accuracy, line and load errors must be combined under their specified conditions; the load regulation table starts at 100 µA. During BQ open-circuit sampling, the load can be below this range. A casual “5 V ±2% = 5.1 V guaranteed maximum everywhere” is unsupported.
- Maximum dropout is 0.5 V at 50 mA and 1.2 V at 150 mA. No guaranteed 100 mA figure is supplied. Weak-light/dawn operation below its 2.7 V minimum input is lost; the original harvester can cold-start from about 0.6–0.7 V under specified conditions.
- BQ's 80% sample of a regulated 5 V is about 4 V. During charging it attempts to pull the LDO output down while the LDO tries to regulate 5 V. A current-limited panel can force dropout, with the solar operating point roughly 4 V plus dropout. That can work, but coupled-loop stability, energy capture and repeated MPPT sampling need a source-impedance sweep.
- Even `5.1 V × 0.8 × 100 mA = 408 mW` exceeds the recommended 400 mW input power. The panels' 50 mA labels are not maximum Isc, and TPS709's own current limit is far too high to enforce 100 mA. A lower voltage variant gives more headroom but still needs a bounded source-current design.
- **Do not tie EN directly to the panels.** TI allows EN left floating using its internal enable current; the EN input has a much lower absolute limit than VIN.
- Its output capacitor must retain at least 1.5 µF effective capacitance, with the specified ESR. The BQ input capacitor may be shared only after checking its actual DC-bias and temperature derating plus both devices' placement requirements. Add an appropriate LDO input capacitor. Reverse leakage figures are typical; active reverse protection depends on output voltage and is not unconditional below 1.8 V.

[TI TPS709](https://www.ti.com/lit/ds/symlink/tps709.pdf)

A series LDO does not continuously dissipate 0.5 W when storage is full: load then falls toward the circuit's quiescent currents. During charging dissipation is `(Vpanel−VLDOout) × I` and must be calculated using cold Voc/current curves, not the nameplate alone. Added mass/cost should use the sourced SOT-23 part and ceramics rather than an invented precise total. A clamp-and-current-limiter or a harvester with suitable input ratings remains an alternative if the LDO cannot preserve useful operation.

## Existing thresholds, GNSS and measurement obligations

| Function | Actual divider | Nominal | Cold screening interval |
|---|---|---:|---:|
| Buck output | R6 8.25 MΩ / R7 4.75 MΩ | 3.3116 V | 3.1785–3.4497 V |
| VBAT_OK falling | R3 4.75 MΩ / R5 4.42 MΩ | 2.5103 V | 2.4188–2.6051 V |
| VBAT_OK rising | (R3+R4), R4 3.65 MΩ / R5 | 3.5095 V | 3.3662–3.6584 V |

The computed buck interval is below MAX-M10S's 3.6 V maximum, but nominal 3.3116 V is slightly above the datasheet's cited `<3.3 V` regulation test condition; this is an engineering screen, not a guaranteed rail envelope. The BQ's 93 mA minimum / 110 mA typical output-current figures are specified at VSTOR 3.3 V and VOUT 1.8 V, not a guaranteed 3.3 V cold radio-plus-GNSS budget. Its VBAT-to-VSTOR switch resistance is up to 1.5 Ω under the stated test condition, larger than the capacitor's room-temperature ESR. At 100 mA, that can mean 150 mV before other losses. Measure simultaneous GNSS startup and TX supply sag.

The audit found that `firmware/include/stratolink_pins.h` called the thresholds 2000/1620 mV and inferred them from boot near 2 V. That inference is invalid with VOUT_EN tied to VSTOR. The release task has corrected diagnostic metadata to 3510/2510 mV and uses an explicit `STRATOLINK_HW_V1_1` flag for the new 5041 mV/9.55 J values, retaining the original 5363 mV/11.2 J values for v1. The boot observation remains an observation; runtime power policies were not changed. Parent verification built v1.1 and checked four preprocessing cases, independently of the microphone flag. Verify PB5 edges against measured VSTOR during the pilot. VBAT_OK is VSTOR-referenced through the existing 100 kΩ resistor; MCU input tolerance must be checked against its exact pin mode before claiming that path is protected.

Normal pilot qualification should record actual R1/R2 charge plateau, both capacitor-cell voltages, source Voc/Isc/MPPT behaviour, balancer current/oscillation at cold/startup and imposed cell imbalance, and rail sag during concurrent GNSS/radio load. Operation below the capacitor's −40°C rating is not established by its thin shape or altitude; board temperature and low-pressure thermal behaviour remain measured limits.

Install C5 **after** reflow and board cleaning, using the manufacturer's approved secondary hand/hot-bar process. Its DMF datasheet excludes ordinary infrared/hot-air/wave reflow; do not include it as a normal JLC reflow placement. The flat capacitor is 1 F nominal, 0.8–1.2 F tolerance, 5.5 V stack / 2.75 V per cell, −40…+70°C, 1.3 g. These are ratings of the retained part, not a substitute for individual-cell monitoring during the pilot.

## Reproduction and evidence

- `build_balancer_candidate.py` → `extract_route_geometry.py` → `route_balancer.py` → `finalize_balancer.py` builds the isolated routed source; `freeze_balancer.py` copies and hashes it without overwriting a previous freeze. KiCad may generate fresh internal UUIDs for newly instantiated footprint sub-items; the geometric/electrical proof is independent of those new UUIDs.
- `balancer-final-candidate.json` and `thermal-author-manifest.json`: immutable source hashes, exact changed-object scope, supplier-field parity, local thermal dimensions and route-resistance calculations. All original library files remain byte-identical; the only added symbol library is `Stratolink_Power.kicad_sym`.
- `native-route-verification.json`: native report hashes, conditions and dispositions. Raw native reports are retained in external scratch alongside the frozen candidate.
- `review_integrated_power.py` → `integrated-power-review.json`: final merger delta, native pad/net proof, metadata, thermal scope and enabled DRC review for the exact integrated hashes.
- `calculate_limits.py` → `limits.json`: explicit equations, assumptions and comparison cases.
- `compare_power_topology.py` → `v1-topology-comparison.json`: current-v1 pad-net comparison.
- `actual-netmap.json`: frozen actual net/value evidence.
- `flight-screen.json`: original CSV hash, extrema, threshold counts and limitations.
- `source-manifest.json`: exact downloaded primary documents and SHA-256 values. Large downloaded PDFs live in external scratch; official URLs are recorded for recreation.

No simulation here claims to reproduce electrochemical leakage, low-pressure cooling or the unmeasured panel I–V curve. The numerical margins are useful for choosing a pilot design; the explicitly listed measurements are required to qualify it.
