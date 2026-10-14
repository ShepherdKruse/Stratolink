# Capacitor and power peer review : 2026-10-14

**Keep C8 and C21 for the current pilots.** C8 is radio supply decoupling consistent with RAK's own reference circuit. C21 adds distributed bulk capacitance on the upper 3.3 V rail; no measured evidence establishes it as redundant. Neither part is physically large: both are 0603. A more useful concern is DC-bias loss in the actual MLCCs, followed by GNSS supply impedance and bypass placement. No CAD, BOM, cart or Git changes were made by this review.

The review reads the canonical PCB SHA-256 `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c` and schematic `a06740b35d07d7b81999f7ace2a7a7ff02e185ca3e46a664630bd4bbd00c54b7`. A fresh schematic export and native PCB snapshot agree on the capacitor nets. Files: [netlist](current-netlist.xml), [native geometry](native-power.json), [source ledger](sources.json), [manufacturer curve extraction](capacitor-curves.json), [charge-balance screen](power-screen.json).

## Actual parts and roles

| Reference | Exact fitted part | Value / package / rating | Native nets and role | Recommendation |
|---|---|---|---|---|
| **C8** | Samsung CL10A106KP8NNNC, C19702 | 10 µF ±10%, 0603, 10 V X5R | +3.3 V–GND, beside U2 radio VDD; paired with C7 100 nF | **Keep.** Do not remove the radio's local bulk bypass. |
| **C21** | Same as C8 | Same | +3.3 V–GND, upper sensor/rail region; upstream of the GNSS bead | **Keep for pilots.** Only consider removal after controlled A/B rail-transient measurements. It is not a dedicated filtered GNSS capacitor. |
| C2 | Samsung CL10A475KP8NNNC, C1705 | 4.7 µF ±10%, 0603, 10 V X5R | +SOLAR–GND, U1 VIN_DC input buffer | Keep; investigate effective-capacitance/input-ripple margin. |
| C3 | Same as C2 | Same | VSTOR–GND, boost output buffer, paired with C4 100 nF | Keep; investigate biased capacitance and cold/startup margin. |
| C6 | Samsung CL21A226MAYNNNE, C602037 | 22 µF ±20%, 0805, 25 V X5R | +3.3 V–GND, buck output capacitor beside L2 | **Keep.** Do not shrink by matching nominal capacitance alone. |
| C16 | Same as C2 | 4.7 µF | +3.3 V–GND, additional distributed rail bulk | Keep within the present baseline. |
| C10 | Samsung CL05B104KO5NNNC, C1525 | 100 nF, 0402 | Filtered `Net-(U3-VCC)`–GND, after FB1; only external bypass on this net | Keep; review relocation close to U3's supply pins. |
| C5 | DMF4B5R5G105M3DTA0 | 1 F dual-cell storage | /VBAT–GND, with midpoint balancing | Separate reservoir before the buck; not a substitute for local 3.3 V decoupling. |

**C8 and C21 are all the 10 µF capacitors in the current design.** The two 0603 bodies are each nominally 1.60 × 0.80 × 0.80 mm. [Samsung exact 10 µF family](https://product.samsungsem.com/mlcc/CL10A106KP8NNN.do), [4.7 µF family](https://product.samsungsem.com/mlcc/CL10A475KP8NNN.do), [22 µF family](https://product.samsungsem.com/mlcc/CL21A226MAYNNN.do).

## Manufacturer requirements, with the nominal/effective distinction

TI's BQ25570 recommended-operating table (§6.3) lists **CIN ≥4.7 µF, CSTOR ≥4.7 µF, COUT minimum 10 µF / nominal 22 µF**, and equivalent storage ≥100 µF. The output pin description and §8.1.4.4 recommend ≥22 µF for most applications. These are not interchangeable statements: **22 µF is not the table's hard lower bound**. The inspected text does not explicitly say whether its listed values are nominal purchase values or guaranteed capacitance after DC bias. Low leakage, low ESR, short capacitor loops and the parallel VSTOR high-frequency bypass matter; larger VSTOR capacitance can extend cold start. [TI BQ25570, §§6.3, 8.1.4, 10.1](https://www.ti.com/lit/ds/symlink/bq25570.pdf).

TI's own EVM uses nominal 4.7 µF **0805 X7R** input/store parts (`C0805C475K9RACTU`, `LMK212B7475KG-T`) and nominal 22 µF **0805 X5R** output (`JMK212BJ226MG-T`). That is evidence against treating zero-bias nominal numbers as guaranteed operating minima, and against assuming any smaller same-value part has equivalent behavior. The present 0603 input/store parts differ from those EVM orderables. [TI EVM guide, Table 2](https://www.ti.com/lit/pdf/SLUUAA7).

The RAK3172 datasheet points to RAK3272S as its minimum reference circuit. The [manufacturer schematic](https://images.docs.rakwireless.com/wisduo/rak3272s-breakout-board/datasheet/rak3272s-schematic.png), visually inspected and cached, puts **10 µF plus 100 nF on VDD**. The module documentation reports 87 mA at 20 dBm/868 MHz; that is a specified operating example, not a guaranteed current for every frequency/power setting. C8/C7 implement that local-decoupling pattern. [RAK3172 datasheet](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/).

## Actual DC-bias evidence

The script extracts Samsung's public `datasheetData` curve points from the exact family pages and interpolates linearly. These are **typical design-reference curves, not guaranteed production limits**. C8/C21 and C2/C3 curves use 1 kHz / 1 Vrms; C6 uses 120 Hz / 0.5 Vrms. Actual small-ripple capacitance, lot tolerance, aging and combined bias/temperature behavior still require characterization.

| Part / operating screen | Nominal | Typical capacitance from DC-bias curve at 25 °C |
|---|---:|---:|
| C8 or C21 at 3.3 V | 10 µF | **4.43 µF** |
| C6 at 3.3 V | 22 µF | **13.86 µF** |
| C16 at 3.3 V | 4.7 µF | **2.10 µF** |
| C2 at illustrative 4.0 V input | 4.7 µF | **1.69 µF** |
| C3 at illustrative 5.041 V VSTOR | 4.7 µF | **1.31 µF** |

The last two voltages are analysis points, not measurements of the actual solar/VSTOR waveforms. At 5 V bias, Samsung's combined-bias temperature curve for the 4.7 µF part gives about **1.35 µF at −40 °C** versus 1.44 µF at 25 °C. Its separate 25 °C DC-bias curve gives 1.32 µF at 5 V; the difference itself cautions against presenting a finely rounded typical curve as a guaranteed bound. The 10 µF combined curve is at 5 V and C6's is at 12.5 V; neither directly guarantees behavior at the actual 3.3 V rail.

**This identifies a qualification risk, not a newly proved hard-limit violation or a reason for a blind capacitor increase.** C6's typical 3.3 V value remains above TI's 10 µF table minimum. The input/store parts lose substantially more than their nominal labels suggest. Measure ripple, startup and transient behavior and seek a manufacturer minimum-effective-capacitance interpretation before freezing a smaller population.

As a deliberately simplified charge-balance illustration, the four rail bulk parts C6/C8/C21/C16 sum to 46.7 µF nominal but about **24.82 µF** using those typical 3.3 V curves. Omitting C21 reduces that to **20.39 µF**; omitting both 10 µF parts to **15.96 µF**. A 100 mA, 10 µs current deficit would produce idealized droops of **40, 49 and 63 mV**, respectively. This is `ΔV = IΔt/C`, not a closed-loop regulator simulation: it ignores feedback, ESR, ESL and trace impedance, and the distant capacitors are not interchangeable at high frequency. They cannot supply a sustained radio transmission on their own.

## Smaller and same-footprint candidates

These are **characterized candidates for qualification, not approved substitutions or stock commitments**. Supplier stock, leakage, terminal geometry, aging and final assembly must be rechecked before any BOM change.

| Candidate | Possible use | Primary verified specifications / typical screen | Decision |
|---|---|---|---|
| [CL05A106MQ5NUNC](https://product.samsungsem.com/mlcc/CL05A106MQ5NUN.do) | Smaller C8/C21 | 0402, 10 µF ±20%, 6.3 V X5R; **3.75 µF at 3.3 V**, about 15% below the present part's typical value; different test amplitude | Exists, but not an electrically equivalent drop-in. Keep present 0603 for pilots. |
| [CL10A226MP8NUNC](https://product.samsungsem.com/mlcc/CL10A226MP8NUN.do) | Same-footprint C2/C3 or smaller C6 | 0603, 22 µF ±20%, 10 V X5R; **6.83 µF at 5.041 V**, **10.46 µF at 3.3 V**; 5 V combined-bias curve gives 5.87 µF at −40 °C before tolerance | Plausible C2/C3 experiment; increased VSTOR cold-start charge is a tradeoff. Not an approved smaller C6. |
| [CL10A106KA8NRNC](https://product.samsungsem.com/mlcc/CL10A106KA8NRN.do) | Same-footprint C2/C3 | 0603, 10 µF ±10%, 25 V X5R; **4.68 µF at 5.041 V** before tolerance | Voltage rating alone does not guarantee enough effective capacitance. Not selected. |
| [CL21A476MPYNNNE](https://product.samsungsem.com/mlcc/CL21A476MPYNNN.do) | Same-footprint C6 | 0805, 47 µF ±20%, 10 V X5R; **23.17 µF at 3.3 V** before tolerance | Useful measurement candidate if output transient margin needs improvement; not required by current evidence. |

Shrinking both 10 µF bodies to the cited 0402 candidate saves only **1.56 mm² of nominal body area and 1.548 mm³ of body volume**. It does not automatically shrink the PCB or its courtyards; mass savings were not measured or specified. This is a small optimization compared with introducing an unqualified rail change.

## GNSS supply and placement follow-up

The native circuit places FB1 in series with all three U3 supply pins VCC/V_IO/V_BCKP. C10 is the only external capacitor after that bead. Its supply pad is **12.27 mm straight-line** from U3.VCC8; actual routed distance is longer. C8 is **3.70 mm** from radio VDD24, and C21 is **5.44 mm** from C6's supply pad; these are pad-center distances, not extracted loop inductance.

u-blox's integration manual advises no more than **0.2 Ω series resistance** on VCC. Its datasheet calls for a supply capable of **100 mA startup inrush**; normal average acquisition current is much lower. [Integration manual §4.1.1](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf), [datasheet §4.2](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf).

The fitted **BLM15AG601SN1D** bead has **0.52 Ω maximum initial DCR**, 600 Ω at 100 MHz and 300 mA current rating in Murata's primary table. Thus the chosen part does **not guarantee** the 0.2 Ω recommendation, even before trace resistance. At 100 mA, 0.52 Ω corresponds to 52 mV resistive drop; this is not a measured startup waveform or proof of past GNSS failure. [Murata BLM15 specification, rating table](https://www.murata.com/products/productdata/8796740059166/ENFA0018.pdf?1641439816000=).

**Recommended follow-up:** move/retain a bypass at the U3 supply-pin side, assess a lower-DCR same-size bead with noise measurements, and capture supply directly at U3 during startup and radio TX. Do not blindly remove the filter or move C21 across it: doing so changes filter damping, inrush and the upstream rail. The direct Murata PDF download was blocked; its primary indexed table and the existing exact supplier record independently agree on 0.52 Ω. No visually inspected local Murata PDF is claimed.

The existing LBOOST trace crossing beneath GNSS RF is handled by the separate RF review. The initial west-side RF detour was rejected because it lengthens the feed and worsens other return-path conflicts. Moving L1 entirely to the right of the existing RF feed would require a wider power-placement redesign. A separate GNSS placement study is in progress; this power review does not approve that layout or alter the switching loops.

## Physical tests that settle the decisions

1. Measure C2/C3/C6 and proposed replacements under actual DC voltage, cold/room temperature and representative small AC stimulus; record method, aging and part lot.
2. Scope VIN, VSTOR, buck output and U2/U3 local supply pads using short ground springs. Cover weak-sun cold start, full solar, low stored voltage, GNSS startup, maximum intended radio power and simultaneous loads. Record minimum voltage, ripple and resets.
3. If size reduction remains useful, A/B C21 omission on a sacrificial pilot; preserve C8/C7 and compare identical conditions. Do not extrapolate room-temperature idle behavior to cold TX or sunrise recovery.
4. Qualify GNSS filter/bypass alternatives with C/N₀, fix recovery and supply waveforms during radio/switching activity. Layout or filter changes need new DRC, net parity, manufacturing exports and supplier review.

Reproduction: run `snapshot_power.py` with KiCad's bundled Python, then `analyze_cap_curves.py` and `model_power.py` with Python 3. They write only this review directory and never save the input PCB. Cached HTML contains exact manufacturer curve points and source hashes; no speculative SPICE model or unmeasured operating guarantee is presented.
