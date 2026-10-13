# AS7331 v1.1 hardware integration

The user selected AS7331 for the canonical v1.1 design and authorized omitting an unavailable UV sensor from the first three assembled pilots. This supersedes the previously undecided UV item in the sourcing review. Work is on `alpha/hardware-v1.1`, with the final project in `hardware/pcb`.

## Selected circuit and pilot population

- U6: **ams AS7331-AQFM, C20482877**, 16-terminal OLGA, separate UVA/UVB/UVC channels, 3.3 V supply, address **0x74**.
- R27: **Vishay MCU0805MD3304BP500, C4313228**, 3.3 MΩ, ±0.1%, ±25 ppm/K, 0805. The primary datasheet lists 4.6 mg excluding solder. This meets the sensor reference requirement; a generic 100 ppm/K resistor does not.
- C14 and C23: **Samsung CL05B104KO5NNNC, C1525**, one 100 nF bypass for each sensor supply.
- READY stays unconnected; SYN and address pins have defined ground ties for polled command-mode use. Analog and digital ground return locally to the shared board ground.
- The complete circuit remains populated in CAD. The initial manufacturing variant **omits only U6** and retains the support circuit. Its identity-bound [population profile](manufacturing/pilot-population.json) controls both BOM and CPL. All 57 pilot designators are selected with the exact MPN/LCSC matches in the saved JLC draft; U6 alone is omitted. Cart selection does not reserve stock.
- Matching initial firmware: **`stratolink_v1_1_uv_dnp`**. It performs no UV communication and transmits unavailable UV/lux values. The former v1.1 target still expects the earlier LTR390 layout; a populated AS7331 requires a dedicated validated driver and raw science telemetry.

Sourcing observations and exact part evidence: [sourcing record](sourcing/README.md). Native footprint, routing and independent verification results are recorded under `cad/` and `review/`; the final [canonical record](../../../hardware/pcb/README.md) and [package manifest](../../../hardware/gerbers/v1.1-pilot/manifest.json) identify the reviewed source hashes.

## What this enables, and what remains an experiment

AS7331 is the best compact integrated candidate among the examined parts for separate UV-band measurements on this existing 3.3 V board. It is not a drop-in LTR390 replacement: it needs new lands, local support circuitry, routing and firmware. It also has no visible-light ALS channel. Package mass is not specified in the inspected primary sensor datasheet; no measured total circuit mass is claimed.

At 3.3 V the specified active current is 1.42 mA typical / 2 mA maximum at the table conditions: 4.686 / 6.6 mW. A one-second measurement per minute followed by maximum specified 1 µA power-down gives **113.245 µW** sensor-only average. MCU, bus, converter and restart costs are additional; this is an illustrative duty cycle, not a selected scientific exposure. Standby is much more expensive and must not be confused with power-down. Daytime measurement windows, cold behavior and actual installed supply margins need bench validation.

The operating limit is **−40…85 °C**. Actual die temperature at low pressure must be checked; a vendor listing's +105 °C label is not the primary operating specification. The AS7331 internal temperature sensor is for rough compensation and does not replace TMP117.

Separate UV channels enable an **experimental ozone column above the balloon**, not local ozone concentration or an automatically accurate vertical profile. Broad-band ratios still depend on the spectrum, pointing, clouds/aerosols, channel gain, saturation and temperature. The manufacturer recommends incidence within ±10° to avoid interference-filter shifts. Its design guide also warns that strong solar visible/infrared light can leak through the roughly OD3 blocking and overwhelm a weak UV channel; blocking optics and measured correction may be necessary. An unobstructed chip does not enforce an angular limit.

Before claiming ozone measurements: build and characterize the collector/aperture and any blocking filter; measure dark, linearity, saturation, angular, thermal and out-of-band response; retain raw channels and exposure/gain settings; fit a spectral forward model and validate on independent calibrated observations. The UV-DNP pilots provide none of those UV measurements. [Independent primary-source requirements](review/requirements.md).

## Programming contacts

J3/J4 beside the RAK module are already enlarged ordinary plated through-hole contacts. They retain 0.50 mm holes and 1.00 mm pitch, with 0.88 mm front lands and 1.20 × 0.88 mm rear lands offset 0.12 mm inward. They are not castellated edge connectors. The rear oval lands provide about 68% more exposed copper than the current front lands after subtracting the hole; solder temporary wires from the rear and control solder volume at the approximately 0.12 mm neighboring gap. The 0.40 mm board and existing hole centers stay unchanged. [Geometry review](../headers/README.md).

No checkout, component purchase, firmware flash or public push is part of this integration. The user has authorized a reviewed JLC cart draft for five fabricated boards and three assembled pilots; final factory CAM acceptance and physical pilot qualification remain separate from a cart entry.

## Corrected board finish

The user clarified that the unwanted layer is **silkscreen** and explicitly requested **green solder mask**. This supersedes all earlier bare-board/no-mask instructions. The promoted integration removes silkscreen artwork from the board and active local footprint libraries, retains selective green-mask openings over soldering lands, and exposes copper solar polarity symbols. Ordinary vias are tented; solar banks and positive PTH lands remain solderable. Final native and manufacturing checks passed with the green-mask/no-silkscreen profile; factory CAM approval remains outstanding.

## Saved JLC pilot draft

The [JLC cart](https://cart.jlcpcb.com/shopcart/cart) contains **fabrication-review_Y24**, PCB **Y24-2680969A**, PCBA **SMT026101364685-2680969A**: **five PCBs / three assembled**, Standard Both Sides. Independent selection review passed for all 57 exact MPN/LCSC matches. Top/bottom supplier previews were inspected, including C14/C23/R27, relocated C21 and U1/U2/U3/U4/U5/U7/U8 orientations. U6 is absent; no browser rotation changes were made.

The draft is **US$332.47** (US$70.63 PCB + US$261.84 assembly), excluding shipping, tax and any advanced-remark review changes. Saved settings are green 0.40 mm FR4, 1 oz copper and ENIG with 1 µin gold. The **71.36 × 71.30 mm** supplier rail envelope surrounds the unchanged **23.36 × 57.30 mm** board. Production-file and parts-placement confirmations are enabled, with manual approval and no automatic changes. Factory CAM, mask/rail disposition, physical testing and the later populated-AS7331 driver/optics remain outstanding.

The old Y22 fifteen-board draft was left untouched; its out-of-stock warning belongs only to that older item. **No checkout or payment was made.** [Saved cart, selection and placement evidence](jlc/README.md).
