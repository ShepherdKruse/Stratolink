# Hardware Design
PCB layouts, circuit diagrams, and mechanical designs for Stratolink pico-balloon hardware.

## Directory Structure
- `/pcb` - PCB design files and project files
- `/gerbers` - Manufacturing-ready Gerber files and drill files
- `/3d-models` - 3D enclosure and mechanical designs
- `/docs` - Hardware documentation and specifications
  
## Hardware Components
1. [RAK3172-9-SM-NI](https://www.lcsc.com/product-detail/C18548052.html?s_z=n_RAK3172) LoRaWAN Module (STM32WLE5)
    - Exact BOM part is RAK's 9xx MHz SKU for US915/AU915/KR920/AS923; EU868 is assigned to the separate `-8` SKU. The wire monopole is modeled across 868/915/923 MHz, but antenna bandwidth does not qualify the module's internal RF matching. Flight-3 EU868 reception is operating evidence only pending conducted/cold RF qualification.
    -     [4269](https://www.digikey.com/en/products/detail/adafruit-industries-llc/4269/10313908) sprint antenna
    - Can use STM32's `VREFINT ADC` for voltage monitor on both solar cells and supercap
    - 1.69µA sleep current
2. uBlox [MAX-M10S-00B](https://www.lcsc.com/product-detail/C4153167.html?s_z=n_u-blox%2520Max%2520m10s)
    - no EEPROM, need something like `CFG-NAVSPG-DYNMODEL=8` sent after each restart
    - 262,000 ft upper bound - COCOM compliant
3. Power
    - [Solar Cell](https://www.zachtek.com/product-page/copy-of-solar-cell-for-pico-balloons-polymer-4-8v-50ma)
        - x2 4.8V/50mA cells
    - [BQ25570](https://www.lcsc.com/product-detail/C506250.html?s_z=n_BQ25570)
        - TI nano-power PMIC, 330mV cold start
    - [DMF4B5R5G105M3DTA0](https://www.cap-xx.com/products/dmf4b5r5g105m3dta0)
        - 1F, 5.5V, 40mΩ ESR
        - Qualification warning: the production BQ25570 divider is 8.25 MΩ /
          4.22 MΩ using ±1% parts. Its 5.363 V nominal threshold is not a
          tolerance-safe 5.5 V bound; the conservative source audit reaches
          5.544 V before resistor temperature coefficients and 5.592 V across
          the BQ25570 operating range. Keep the current payload shaded until the divider is
          lowered/qualified or a calibrated controlled-light test establishes
          adequate exact-assembly margin. See
          `analysis/diagnostics/supercap_charge_ceiling_audit.py`.
        - Source-screened rework candidate: Vishay
          `CRCW04027M50FKED` (7.50 MΩ, 0402, ±1%, ±100 ppm/K), the same
          lead-free D/CRCW e3 family as R2. The modeled -40..85 °C upper bound
          is 5.251917 V, leaving 248.083 mV to 5.5 V. With CAP-XX's ±4%
          internal cell matching, the worst initial cell screen is 2.730997 V,
          only 19.003 mV below 2.75 V. This is not assembly
          qualification: verify delivered identity, clean the high-impedance
          divider before C5 installation, and measure the fitted threshold.
        - Hard balance gate: this is a dual-cell, three-terminal part, but PCB
          pad 3 is unconnected. CAP-XX says it supplies no internal balance and
          highly recommends balancing for every series-connected module. Do
          not install C5 until an application-specific low-leakage midpoint
          network is designed and the darkness budget is updated. See
          `analysis/diagnostics/supercap_balance_audit.py`.
        - One active-balance candidate from CAP-XX AN1002 is TI
          `TLV8801DBVT` (SOT-23-5, -40..125 °C) and two Vishay
          `MCA1206MD1005BP100` 10 MΩ / 0.1% / 25 ppm/K resistors, with CAP-XX's
          22 Ω midpoint resistor. The TI maximum quiescent-current screen is
          0.952 µA including the reference divider and lowers the same
          baseline-only runtime to 9.115 h. This is not yet a buildable flight
          ECO: the full-screen initial mismatch asks for 4.774 mA while TI
          specifies 4.7 mA only as a typical short-circuit value. Use a
          qualified daughterboard/flex and prove startup, saturation,
          correction time, RF stability, and both cell voltages before fitting
          C5; do not dead-bug an unreviewed circuit onto the flight board.
        - A second, purpose-built candidate is ALD `ALD910025SALI`, a dual
          supercapacitor auto-balancing MOSFET in SOIC-8. It eliminates the
          always-on divider/op-amp and falls toward pA current below threshold.
          The source-bound typical model gives about 114.683 µA net
          equalization at the worst initial 4% mismatch and 9.298 h darkness
          runtime at 25 °C with the minimum 2.48 V threshold. This is not a
          worst-case guarantee: ALD limits the 25 °C threshold and channel
          offset, but its current curve and temperature coefficients are
          typical-only. The `SALI` rating also stops at -40 °C, 2.1 °C warmer
          than Flight 3's coldest telemetry. Treat it as a strong alternative
          for reviewed daughterboard/flex and HIL, not as a qualified drop-in.
          ALD's family data offers custom M-suffix -55..125 °C screening, but
          no exact ALD910025 military orderable is bound; obtain a quote and
          certificate, and remember that C5 itself remains rated to -40 °C.
          See the comparative decision record in
          `analysis/diagnostics/STRATOLINK2_SUPERCAP_BALANCER_DECISION_20260725.md`.
4. Audio
    - TDK InvenSense [MMICT390200012](https://www.lcsc.com/product-detail/C3171752.html?s_z=n_MMICT390200012)
        - Use cases: thunder detection, aircraft proximity, envelope stress monitoring
5. Pressure Sensor
    - TE [MS5611](https://www.lcsc.com/product-detail/C15639.html?s_z=n_MS5611)
        - seems like only viable option above 40k feet. 10-1200 mbar
6. Tempature Sensor
    - [TMP117](https://www.lcsc.com/product-detail/C2871893.html?s_z=n_TMP117)
7. Spectral Sensor
    - [LTR-390UV-01](https://www.lcsc.com/product-detail/C492374.html?s_z=n_LTR-390UV-01)
          - specfically intrested in UV, potentially to calcuate ozone saturation
8. Accelerometer
    - [LIS2DH12TR](https://www.lcsc.com/product-detail/C110926.html?s_z=n_LIS2DH12TR%2520)
          - burst/free-fall detection. can trigger rapid beacon mode during fall.
          
### Weight Budget
Estimated weight budget may be found [here](https://docs.google.com/spreadsheets/d/1s64bTjT7GJ9_eSN0aLWiRmVTLvOQ8GIDuoYdtb-1NMI/edit?usp=sharing).

## Notes
- The older 16-hour darkness calculation (`2 µA`, `0.5 V` drop, exact `1 F`)
  is superseded. The selected part is specified at 0.8-1.2 F, and the only
  board profile measured 33-35 µA with J-Link attached (a conservative bench
  upper bound, not a debugger-free flight value). From the present nominal
  5.363 V ceiling to the conservative 3.32 V Flight-3 reported plateau, the
  0.8 F part screens
  at 13.759 h for 33 µA with zero capacitor leakage, or 11.075 h for 35 µA
  plus the datasheet 6 µA room leakage limit—before GPS, sensing, TX/RX,
  watchdog wakes, cold, aging, or sag. See
  `analysis/diagnostics/supercap_night_reserve_audit.py`; fitted-cap darkness
  and recovery HIL is required.
- The 7.50 MΩ charge-ceiling candidate reduces the same 0.8 F / 35+6 µA
  baseline-only screen to 9.326 h before balance-circuit overhead. The
  source-bound TLV8801 maximum-current screen reduces that to 9.115 h before
  capacitor leakage beyond the 6 µA allowance or active GPS/radio cycles. Voltage
  safety, individual-cell balance, and darkness reserve must be
  closed together with the exact fitted capacitor; neither model is a launch
  qualification by itself.
- The ALD910025 typical-curve integral predicts 9.298 h at 25 °C and 8.962 h
  at 85 °C (using its 25 °C minimum threshold plus typical threshold tempco).
  Because those curves lack worst-case limits, measured exact-assembly
  darkness current remains the controlling gate.
- Standard FR4 (0.4mm maybe) is sufficient here

## Design Tools
#### PCB Design
- KiCad - Primary PCB design tool for schematics and layouts
- Production files exported as Gerber files in `/gerbers`

#### 3D Mechanical Design
- Fusion 360 - Primary CAD tool for enclosures and mechanical designs
- CAD files provided in both formats:
  - `.f3d` - Native Fusion 360 format (editable)
  - `.step` - Universal CAD format for compatibility
