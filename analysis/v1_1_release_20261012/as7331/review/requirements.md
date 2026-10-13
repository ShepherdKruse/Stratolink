# Independent AS7331 integration review requirements

Reviewed 2026-10-13 against ams DS001047 v4-00 (2023-03-24), with the primary pin, application and package figures rendered and visually inspected. The PDF has one unnumbered cover: printed pages 7, 63 and 64 are PDF pages 8, 64 and 65. This review does not qualify an ozone product or establish actual part supply.

## Electrical acceptance

- AS7331-AQFM and AS7331-AQFT are the same OLGA16 electrical device in 1,000- and 5,000-piece reel packaging, respectively (printed p6). Preserve an exact manufacturer ordering code in the BOM; do not infer the stock of one supplier alias from another.
- Pins 1, 2, 5, 6, 15 and 16 are analog ground VSSA; pin 11 is digital ground VSSD. Connect the analog and digital return locally under or near the device (p63); avoid routing radio/converter return through the analog reference loop.
- Pin 3 VDDA and pin 10 VDDD require 2.7–3.6 V. Figure 58 shows one local 100 nF capacitor for each sensor supply; its third 100 nF capacitor belongs to the controller. Both rails from the same 3.3 V source avoid differential sequencing; absolute VDDA minus VDDD is limited to ±0.3 V. A 5 V absolute supply limit is not an operating rating.
- Pin 4 REXT connects to VSSA through 3.3 MΩ, ±1%, with temperature coefficient at most 50 ppm/K. The exact selected resistor must meet the TCR at this high value; ordinary 0402 1% parts can be 100 ppm/K or worse. Place REXT and supply components on the same PCB side as U6. Keep the reference trace short and clear of other copper to reduce coupling and surface-leakage susceptibility; solder mask does not eliminate leakage around exposed pads.
- Pins 7 A1 and 14 A0 at ground select seven-bit address 0x74, distinct from the existing pressure sensor at 0x76. Pin 12 is SDA and pin 13 is SCL. Verify existing pull-ups and the finished native netlist, not just symbol labels.
- Pin 8 SYN is a digital input. A ground tie is a deliberate defined level for firmware using command mode, not synchronized modes. Pin 9 READY is an output, push-pull by default; leave NC when polled. Do not copy the old sensor's grounded interrupt onto READY.
- Operating ambient and storage range is −40 to +85 °C (p9). Some optical parameters are typical laboratory characterization at 25 °C, not guaranteed accuracy across temperature. The rough internal temperature sensor has ±10 K stated absolute error and must not replace TMP117 as ambient metrology.

## Footprint and assembly acceptance

The package drawing (p64, Figure 59) is a *bottom* view for its contact dimensions; the pin diagram and package top view orient pin 1 at upper left. In a native front-side footprint at 0 degrees, top row is pins 1, 2, 3, 4 left to right; right side 5, 6, 7, 8 top to bottom; bottom row 12, 11, 10, 9 left to right; left side 16, 15, 14, 13 top to bottom.

Nominal package contacts are 0.30 × 0.30 mm (±0.05 mm); row pitch is 0.50 mm. Contact centers relative to body center are:

| Edge | Centers (mm) |
|---|---|
| Top | x = −0.75, −0.25, +0.25, +0.75; y = −1.575 |
| Bottom | x = −0.75, −0.25, +0.25, +0.75; y = +1.575 |
| Left | x = −1.05; y = −0.75, −0.25, +0.25, +0.75 |
| Right | x = +1.05; y = −0.75, −0.25, +0.25, +0.75 |

These are package-terminal centers, not an explicitly recommended PCB land pattern. PCB pad extension and paste reductions are engineering choices to verify for the actual stencil and placement process. The larger corner interval differs from a generic QFN16. Body is 2.60 × 3.65 × 1.09 mm, ±0.10 mm on each overall dimension. Nominal centered optical aperture is 0.950 × 0.950 mm; active sensor extent is 0.680 × 0.680 mm. Package-outline clearance must include tolerances, especially adjacent tall parts or panel wires.

- Freeze the symbol and footprint in the project library and compare all 16 native pads to the library and schematic export.
- User finish clarification (2026-10-13) requires green solder mask and no silkscreen, superseding the earlier bare-board requirement. Remove full-board mask openings, preserve required exposed solar ground banks and through-hole lands, and verify individual apertures/mask webs around U6 and fine-pitch TMP117. Preserve selective paste; prohibit solder-wettable unintended connections. A clean DRC alone does not qualify the optical LGA assembly process.
- Preserve remaining component pins/nets and footprint geometry except documented local moves needed for U6. Refill ground zones and rerun native parity, DRC, thermal and electrical island checks. Remove only obsolete U6 exceptions.
- Figure 59 specifies only sixteen perimeter terminals and no central exposed pad. A routed via under the unpadded center is not disqualified by an exposed-pad electrical contact, but the package drawing does not qualify this assembly method. If a power or signal via is used there, verify exact land/paste clearances and tenting on both faces in the final source/Gerbers, avoid a solder deposit at the via, and verify tent integrity before later U6 population.
- Optical aperture must remain free of paste, solder, flux residue, glue, tape and coatings. Cleaning guidance is neutral IPA; the device is MSL3 (168 h floor life under stated conditions), with the manufacturer's reflow limits (p67–69). Factory MSL handling and reflow qualification are not demonstrated by CAD.
- Pilot DNP must be an explicit assembly population variant; the selected plan is U6 omitted, C14/C23/R27 populated. Suppress U6 stencil apertures for that pilot or obtain explicit assembler handling; BOM omission alone is not evidence of paste omission. The selected pilot omits only U6 from placement; populate C14/C23/R27 and preserve shared I²C pull-ups and all bypass components needed by other devices. Keep a full-population design BOM and clear later-population orientation information.

## Selected reference resistor and stencil screen

R27: **Vishay MCU0805MD3304BP500**, supplier alias C4313228, is independently consistent with the primary Vishay Document 28952, revision 28-May-2026. The part code decodes as 0805, automotive variant M, D = ±25 ppm/K, 3304 = 3.3 MΩ, B = ±0.1%, P5 = 5,000-piece reel, 00 = standard. The specification table extends the 0805 25 ppm/K / 0.1% range to 7.5 MΩ, so 3.3 MΩ is included. The corresponding 0603 precision range ends at 2 MΩ; it must not be assumed equivalent. General load mode already permits −55…125 °C, which exceeds the sensor's stated temperature range. Other higher-power mode limits do not matter for this few-microwatt reference.

At −40 °C versus a 25 °C reference, the simple bound from 25 ppm/K and ±0.1% initial tolerance is ±0.2625%, excluding aging and PCB leakage. At +85 °C it is ±0.25%. For scale, a parasitic resistance across a 3.3 MΩ resistor must exceed 326.7 MΩ to hold its downward resistance error below 1%, or 3.297 GΩ below 0.1%. These are direct parallel-resistance calculations, not a measurement of this board. Keep the reference area clean and verify high-humidity/condensation behavior.

The candidate's derived 0.35 mm square copper land and 0.30 mm square paste aperture give 0.15 mm nominal inter-land spacing and 73.47% paste-to-copper area. Aperture area divided by stencil wall area is 0.75 at 100 µm stencil thickness, but 0.625 at 120 µm. A 100 µm stencil gives the larger aperture-to-wall ratio and is the conservative starting point for future U6 population, subject to assembler qualification. JLC's live stencil capability table lists 100 µm as a standard thickness and its FAQ gives 100–120 µm as common for fine-pitch BGA/QFN; it does not qualify this specific footprint. The actual solder alloy, paste, stencil finish and final mask geometry still require assembly-process qualification. The datasheet does not publish a recommended PCB pad/stencil pattern.

Primary stencil capability: https://jlcpcb.com/capabilities/pcb-stencil-manufacturing

Primary resistor specification: https://www.vishay.com/docs/28952/mcr0201at-mca1206at.pdf

## Power and optical limits

At 3.3 V: active 1.42 mA typical = 4.686 mW; table maximum 2 mA = 6.6 mW; standby maximum 970 µA = 3.201 mW; power-down maximum 1 µA = 3.3 µW, at stated datasheet table conditions. One second of measurement costs at most 6.6 mJ at that table limit, excluding MCU, I²C and regulator costs. With one second on and 59 seconds in maximum power-down per minute, device-only average is 113.245 µW. Standby is not the low-power state to use for this duty cycle. Actual cold leakage and converter start/stop losses remain measurements.

AS7331 provides separately filtered UVA, UVB and UVC data and no visible ambient-light channel. It enables an experimental ozone-column retrieval, not an automatic calibrated concentration. Broad spectral ratios remain sensitive to cloud/aerosol differences, channel calibration, actual band responses, gain/exposure, stray light, solar angle and filter incidence. A drifting balloon also changes orientation. Preserve raw channels and acquisition settings; reject saturation and invalid conversions. Do not reinterpret channels as visible lux or calibrated UV index.

The manufacturer guidance requires incidence within ±10 degrees to limit spectral filter shifts. An exposed chip on the payload does not by itself meet that condition for arbitrary sunlight. Any diffuser belongs before angle-limiting optics; a diffuser over the die can violate the angular requirement. A separate collector/baffle and full assembly angular calibration remain necessary before an ozone accuracy claim. UVC can be nearly dark beneath most of the ozone layer and is not a replacement for a usable UVB measurement.

The design guide §7.7 (printed pp21–22) adds a solar-specific limitation: out-of-band transmission with roughly OD3 blocking can contribute significant VIS/NIR background when the desired UV band is weak. The manufacturer explicitly notes that solar VIS/NIR power can overwhelm the useful UV contribution and suggests added optical blocking filters where required. Therefore a UVA/UVB ratio should not be treated as ozone-sensitive until sunlight leakage is measured and corrected or filtered. The numerical error cannot be inferred from OD3 alone without the complete wavelength-weighted detector response and illumination spectrum.

The guide's original aperture example is a 1.4 mm diameter hole, 7.9 mm above the active detector, yielding about 7.5 degrees maximum incidence using the 0.34 mm active-area half-width. The die sits 0.345 mm below the outside package surface. These are useful design bounds, not an approved payload attachment design. Keep space for a future opaque collector and verify real UV transmission/stability of every optical-path material.

Low pressure and colder-than-−40 °C air are not qualified by the component rating. Validate actual powered die temperature, optical cleanliness, condensation, PCB surface leakage and operation under the flight thermal envelope. No package mass is stated in the inspected datasheet; a geometrical estimate must not be presented as measured mass.

## Final candidate evidence to produce

1. Exact immutable candidate hashes, plus frozen-source baseline hashes.
2. Independent sixteen-pin semantic map and native pad coordinates versus the visually read package diagram.
3. Fresh schematic export; all retained reference/pin net memberships preserved; only U6 and intended dedicated components changed.
4. Native local copper/paste/clearance review and zero opens/parity errors, with only explicitly reviewed existing warning exceptions.
5. Full-populated and pilot-DNP export comparison; optical/assembly limitations and future population instructions recorded.

Primary source: https://look.ams-osram.com/m/1856fd2c69c35605/original/AS7331-Spectral-UVA-B-C-Sensor.pdf

Optical guideline independently downloaded and checked: https://look.ams-osram.com/m/45d5dfb4a22ecb04/original/AS7331_Design_Guidelines_PD001048_2-00.pdf
