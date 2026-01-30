# Hardware Design
PCB layouts, circuit diagrams, and mechanical designs for Stratolink pico-balloon hardware.
## Directory Structure
- `/pcb` - PCB design files and project files
- `/gerbers` - Manufacturing-ready Gerber files and drill files
- `/3d-models` - 3D enclosure and mechanical designs
- `/docs` - Hardware documentation and specifications
## Hardware Components
1. [RAK3172](https://www.digikey.com/en/products/detail/rakwireless-technology-limited/RAK3172-9-SM-NI/17138034) LoRaWAN Module (STM32WLE5)
    - w/ some wire monopole ant (multi band [868/915/923 MHz] we want to target center frequency ~900 MHz)
    - Can use STM32's `VREFINT ADC` for voltage monitor on both solar cells and supercap
    - 1.69µA sleep current
2. uBlox [MAX-M10S-00B](https://www.digikey.com/en/products/detail/u-blox/MAX-M10S-00B/15712906)
    - no EEPROM, need something like `CFG-NAVSPG-DYNMODEL=8` sent after each restart
    - 262,000 ft upper bound - COCOM compliant
3. Power
    - [Solar Cell](https://www.zachtek.com/product-page/copy-of-solar-cell-for-pico-balloons-polymer-4-8v-50ma)
        - x2 4.8V/50mA cells
    - [BQ25570](https://www.ti.com/product/BQ25570)
        - TI nano-power PMIC, 330mV cold start
    - Murata [DMF4B5R5G105M3DTA0](https://www.digikey.com/en/products/detail/cap-xx/DMF4B5R5G105M3DTA0/16376499)
        - 1F, 5.5V, 40mΩ ESR
4. Audio
    - TDK InvenSense [ICS-43434](https://www.digikey.com/en/products/detail/tdk-invensense/ICS-43434/5872875)
        - I2S digital MEMS microphone, bottom port
        - 3.50×2.65×0.98mm, ~0.03g
        - 1.8V supply, 490µA active / 12µA sleep
        - 65 dB SNR, 120 dB SPL AOP (handles thunder)
        - 50Hz-20kHz frequency response
        - Connects via STM32WL I2S2 peripheral (PA10 = SD)
        - Use cases: thunder detection, aircraft proximity, envelope stress monitoring
5. Environmental Sensors (optional)
    - Pressure
        - TE [MS5611](https://www.digikey.com/en/products/detail/te-connectivity-measurement-specialties/MS561101BA03-50/5277445)? seems like only viable option above 40k feet. 10-1200 mbar
### Weight Budget
Estimated weight budget may be found [here](https://docs.google.com/spreadsheets/d/1s64bTjT7GJ9_eSN0aLWiRmVTLvOQ8GIDuoYdtb-1NMI/edit?usp=sharing).

## Notes
- Supercapacitor-only operation is mathematically viable for 16-hour darkness
    Using C = (I × t) / ΔV with 2µA sleep current, 16 hours (57,600s), 0.5V drop:
    ```
    Minimum capacitance = (2µA × 57,600s) / 0.5V = 0.23F
    Selected: 1F provides 4× margin
    ```
- Standard FR4 (0.4mm maybe) feels sufficient here, *maybe* flexi offers marginal benefit, yet I imagine also significantly impedes design
- ICS-43434 requires 1.8V supply - can tap from BQ25570 regulated output
- ICS-43434 needs acoustic port hole in PCB (~0.5mm diameter minimum)
- *I still need to spec out peripherals for all components on this list, for now this is just the high level stuff*
## Design Tools
#### PCB Design
- KiCad - Primary PCB design tool for schematics and layouts
- Manufacturing files exported as Gerber files in `/gerbers`
#### 3D Mechanical Design
- Fusion 360 - Primary CAD tool for enclosures and mechanical designs
- CAD files provided in both formats:
  - `.f3d` - Native Fusion 360 format (editable)
  - `.step` - Universal CAD format for compatibility
