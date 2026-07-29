# StratoLink-2 supercapacitor balancer decision

Date: 2026-07-25

Status: **blocked pending component review, interposer, and HIL**

## Fixed constraints

- C5 is CAP-XX `DMF4B5R5G105M3DTA0`: a 5.5 V dual-cell,
  three-terminal module with 0.8-1.2 F module capacitance.
- Production C5 pad 3, the cell midpoint, is open. CAP-XX does not provide
  internal balancing and requires an application-specific balance solution.
- The fitted 8.25 MΩ R1 fails the combined BQ25570, 1% resistor, and TCR
  screen: its 5.591979 V upper result exceeds the 5.5 V stack rating, before
  any cell imbalance is considered. It must not remain fitted when C5 is
  installed.
- A lower R1 has not yet been qualified. The earlier 7.50 MΩ candidate passes
  the total-stack screen, but its 5.251917 V upper result puts the worst
  initially matched cell at 2.730997 V, only 19.003 mV below 2.75 V.
  A source-screened 7.32 MΩ candidate lowers those results to 5.170302 V and
  2.688557 V, respectively, increasing initial cell headroom to 61.443 mV at
  a modeled cost of about 0.410 h of baseline darkness reserve. A 7.15 MΩ
  candidate provides 101.525 mV of cell headroom but costs a further 0.386 h.
- Passive 10 kΩ-per-cell balancing adds 252.036 µA and reduces the baseline
  0.8 F darkness model to 1.305 h. It is rejected.
- Flight 3 reported -42.1 °C. The capacitor and most relevant electronics are
  rated only to -40 °C, so neither candidate escapes exact-assembly cold HIL.

The executable sources of truth are
[`supercap_charge_ceiling_audit.py`](supercap_charge_ceiling_audit.py) and
[`supercap_balance_audit.py`](supercap_balance_audit.py). The latter currently
evaluates the 7.50 MΩ reference architecture and fails closed while the
midpoint is open and all physical gates remain absent. That constant is a
comparison baseline, not an approved BOM decision.

The measured trade space is summarized in
[`stratolink2_supercap_divider_frontier.png`](../visualization/stratolink2_supercap_divider_frontier.png).

## Divider frontier

| R1 | Nominal ceiling | Full screen upper | Worst initial high cell | Initial cell margin | 0.8 F baseline darkness | TLV reference, max-IQ model |
|---:|---:|---:|---:|---:|---:|---:|
| 8.25 MΩ fitted | 5.363282 V | 5.591979 V | 2.907829 V | **-157.829 mV** | 11.075 h | 10.819 h |
| 7.50 MΩ | 5.040711 V | 5.251917 V | 2.730997 V | 19.003 mV | 9.326 h | 9.115 h |
| 7.32 MΩ | 4.963294 V | 5.170302 V | 2.688557 V | 61.443 mV | 8.907 h | 8.705 h |
| 7.15 MΩ | 4.890178 V | 5.093221 V | 2.648475 V | 101.525 mV | 8.510 h | 8.319 h |

The darkness values above are boundary comparisons, not mission-runtime
predictions: they use minimum 0.8 F, a conservative 3.32 V endpoint, 35 µA
sleep plus 6 µA capacitor leakage, and no active-cycle, cold, ESR, aging, or
balancer-correction cost. The TLV column additionally uses maximum op-amp IQ
and the reference-divider current.

7.32 MΩ is the current **safer-margin candidate for prototype review**, not a
qualified flight choice. Exact 0402, 1%, 100 ppm/°C parts include Vishay
`CRCW04027M32FKED` and Yageo `RC0402FR-077M32L`; distributor availability was
observed on 2026-07-25 but must be rechecked at procurement. CAP-XX review,
exact delivered-part verification, PCB cleanliness/leakage, fitted-threshold
measurement, and full assembly HIL still govern the final choice.

## Candidate comparison

The comparison below retains 7.50 MΩ as the common numerical baseline so the
balancer architectures can be compared independently from the divider choice.
It must be recalculated for the selected R1 before acceptance.

| Boundary | CAP-XX TLV8801 reference | ALD dual SAB MOSFET |
|---|---:|---:|
| Exact active part | `TLV8801DBVT` | `ALD910025SALI` |
| Other parts | 2 × 10 MΩ `MCA1206MD1005BP100`, 22 Ω | none in the normal path |
| Package | SOT-23-5 plus two 1206 resistors | SOIC-8, 5.0 × 4.05 mm body |
| Temperature rating | -40..125 °C | -40..85 °C |
| Modeled 25 °C baseline darkness | 9.163 h typical; 9.115 h at max op-amp IQ | 9.298 h using typical current curve and min 25 °C threshold |
| Full-screen steady cell margin | 112.648 mV with resistor/TCR/max-offset screen | 114.042 mV with 20 mV max channel offset at 25 °C |
| Worst initial mismatch response | asks for 4.774 mA through 22 Ω | about 114.683 µA net equalization at 25 °C |
| Hard data weakness | 4.7 mA output is typical-only; modeled demand is larger | current curve and threshold tempco are typical-only |
| Extra transient boundary | op-amp saturation/stability | possible reverse-bias current during fast discharge; ALD offers optional Schottky clamps |
| Flight state | unlaid-out and unproven | unlaid-out, procurement unresolved, and unproven |

## Balancer sensitivity to divider choice

Lowering the ceiling improves voltage margin but also reduces both darkness
reserve and the active balancer's initial correction authority. The executable
`divider_architecture_sensitivity` output now screens all three together:

| R1 | TLV max-IQ baseline | TLV initial demand | TLV steady cell margin | ALD 25 °C modeled baseline | ALD initial net equalization | ALD 6 µA/20 mV equilibrium margin |
|---:|---:|---:|---:|---:|---:|---:|
| 7.50 MΩ reference | 9.115 h | 4.774470 mA | 112.648 mV | 9.298 h | 114.683 µA | 102.622 mV |
| 7.32 MΩ safer-margin candidate | 8.705 h | 4.700275 mA | 153.563 mV | 8.895 h | 54.042 µA | 132.729 mV |
| 7.15 MΩ ratio option | 8.319 h | 4.630201 mA | 192.205 mV | 8.505 h | 25.069 µA | 146.785 mV |

The 7.32 MΩ TLV demand is still 0.000275 mA above TI's 4.7 mA typical
short-circuit-current number, and TI specifies no minimum. The 7.15 MΩ demand
falls below the typical number, but that still does not create a guaranteed
minimum or establish stability in saturation. The ALD currents and runtimes
are also typical-curve models. Therefore the lower-divider alternatives reduce
the urgency of the initial imbalance but do not qualify either balancer.
The coupled tradeoff is visualized in
[`stratolink2_supercap_balancer_sensitivity.png`](../visualization/stratolink2_supercap_balancer_sensitivity.png).

## ALD sensitivity model

The ALD exact datasheet defines 1 µA at a 2.50 V cell, with a 2.48-2.52 V
25 °C threshold and 20 mV maximum channel offset. Its current curve is
exponential: 0.1 µA at 2.40 V, 10 µA at 2.60 V, and 100 µA at 2.72 V.
`supercap_balance_audit.py` log-interpolates the published points and integrates

`dt = Cmodule * dVstack / (35 µA + 6 µA + I_SAB(Vstack/2))`.

For equal cell currents, one current—not twice that current—is the equivalent
stack discharge: each shunt dissipates half the stack voltage.

The resulting typical-only screens are:

- 9.298 h at 25 °C with the minimum 2.48 V threshold;
- 8.962 h at 85 °C using the typical -2.2 mV/°C threshold coefficient;
- at a 6 µA cell-leakage mismatch plus 20 mV adverse channel offset, a typical
  25 °C equilibrium of 2.647378 V / 2.604539 V at the full screening ceiling,
  leaving 102.622 mV to the cell rating.

Those numbers rank the architecture. They do not constitute worst-case limits:
ALD explicitly requires measuring every capacitor's leakage, mapping the chosen
limit to cell voltage, and establishing tolerance and temperature margin.

## Decision

The **preferred balancer topology for the next prototype is `ALD910025SALI`**,
provided the exact
industrial suffix can be sourced and CAP-XX agrees that its leakage/current
range is appropriate for this DMF module. It is purpose-built for this job,
uses only the three available capacitor nodes, and has the better modeled night
budget. Do not substitute the readily confused commercial `ALD910025SAL`.

Ask ALD whether a custom M-suffix ALD910025 can be supplied with the family's
published -55..125 °C screening, full electrical limits, traceability, and an
acceptable lead time. Do not invent or order an `ALD910025SALM` code without
manufacturer confirmation. That option would cover the balancer at -42.1 °C,
but the capacitor itself would still be outside its -40 °C rating.

The TLV8801 reference remains the fallback if an exact ALD part or adequate
correction/cold evidence cannot be obtained. Its higher guaranteed
temperature ceiling does not solve the -42.1 °C lower-bound problem, and its
initial output-current margin remains unspecified.

Do not dead-bug either circuit onto the payload. The stock ALD SABMB2 reference
board is 25.4 × 15.24 mm and is development geometry. Create a reviewed,
weighable daughterboard or flex that mates VBAT, midpoint, and GND without
loading or mechanically stressing C5.

## Physical acceptance sequence

1. Obtain CAP-XX review of the 7.32 MΩ safer-margin candidate, the 7.15 MΩ
   alternative, and the selected active topology. Require an explicit answer
   about allowed initial cell imbalance and voltage headroom; do not treat the
   arithmetic screen as a substitute for that review.
2. Procure and verify exact part suffixes; measure each C5 internal cell's
   leakage/capacitance before installation.
3. Review the interposer schematic/layout and decide the ALD Schottky clamp
   population from captured reverse-discharge transients.
4. Rework R1, clean the high-impedance divider twice, and measure the threshold
   before C5 is present.
5. Install C5 discharged and polarized within its hand-solder limits.
6. Capture total voltage and both cell voltages during controlled light ramp,
   maximum light/temperature, dark discharge, GPS start/reset, LoRa TX/RX,
   auxiliary-radio windows, brownout, and sunrise recovery.
7. Repeat through at least the Flight-3 -42.1 °C reported-board envelope while
   measuring component temperatures and requiring normal telemetry/rejoin.
8. Refit the darkness model from measured balancer current, capacitance, ESR,
   active-cycle energy, and cold behavior. No cell may exceed 2.75 V.

## Primary sources

- [CAP-XX AN1002 cell balancing](https://cap-xx-assets.s3.eu-west-2.amazonaws.com/cap_xx_whitepaper_supercapacitor_cell_balancing_d39dd4559f.pdf)
- [ALD810025/ALD910025 exact datasheet](https://www.aldinc.com/pdf/ALD810025.pdf)
- [ALD two-cell circuit note](https://www.aldinc.com/pdf/sabfet_11101.0.pdf)
- [ALD SABMB2 reference-board datasheet](https://www.aldinc.com/pdf/SABMB2.pdf)
- [ALD SAB family datasheet](https://www.aldinc.com/pdf/ALD8100xxFamily.pdf)
- [TI TLV8801 datasheet](https://www.ti.com/lit/ds/symlink/tlv8801.pdf)
- [Vishay D/CRCW e3 resistor datasheet](https://www.vishay.com/docs/20035/dcrcwe3.pdf)
- [DigiKey 7.32 MΩ product filter with Vishay CRCW04027M32FKED](https://www.digikey.com/en/products/filter/chip-resistor-surface-mount/7-32-mohms/52)
- [Yageo RC0402 series datasheet](https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RC_Group_51_RoHS_L_11.pdf)
- [Yageo RC0402FR-077M32L distributor listing](https://www.digikey.com/en/products/detail/yageo/RC0402FR-077M32L/5917749)
