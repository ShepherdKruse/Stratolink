# Hardware Design
PCB layouts, circuit diagrams, and mechanical designs for Stratolink pico-balloon hardware.

## Directory Structure
- `/pcb` - PCB design files and project files
- `/gerbers` - Manufacturing-ready Gerber files and drill files
- `/3d-models` - 3D enclosure and mechanical designs
- `/docs` - Hardware documentation and specifications
  
## Hardware Components
1. [RAK3172](https://www.lcsc.com/product-detail/C18548052.html?s_z=n_RAK3172) LoRaWAN Module (STM32WLE5)
    - w/ some wire monopole ant (multi band [868/915/923 MHz] we want to target center frequency ~900 MHz)
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
4. Audio
    - TDK InvenSense [MMICT390200012](https://www.lcsc.com/product-detail/C3171752.html?s_z=n_MMICT390200012)
        - Use cases: thunder detection, aircraft proximity, envelope stress monitoring
5. Pressure Sensor
    - TE [MS5611](https://www.lcsc.com/product-detail/C15639.html?s_z=n_MS5611)
        - seems like only viable option above 40k feet. 10-1200 mbar
          
### Weight Budget
Estimated weight budget may be found [here](https://docs.google.com/spreadsheets/d/1s64bTjT7GJ9_eSN0aLWiRmVTLvOQ8GIDuoYdtb-1NMI/edit?usp=sharing).

## Notes
- Supercapacitor-only operation is mathematically viable for 16-hour darkness
    Using C = (I × t) / ΔV with 2µA sleep current, 16 hours (57,600s), 0.5V drop:
    ```
    Minimum capacitance = (2µA × 57,600s) / 0.5V = 0.23F
    Selected: 1F provides 4× margin
    ```
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
