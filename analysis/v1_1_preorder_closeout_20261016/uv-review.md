# U6 pre-order review completed

16 October 2026. The AS7331 hardware, placement geometry and populated manufacturing variant have been reviewed against the retained primary documents. **No unresolved U6 schematic, footprint, routing or export defect was found.** This review changes no CAD, manufacturing package or cart. Its purpose is to complete the work possible before JLC supplies an exact sourced part and its assembly-process response.

The exact PCB is `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13`. [Machine evidence](uv-checks.json) records the other source identities and sixteen independent pin checks. [Reproduction script](verify_uv.py) operates read-only on the canonical CAD and populated export. [Physical placement guide](uv-placement-guide.svg) gives JLC an unambiguous pin-1 target independent of its machine-library rotation convention.

## Completed design and package checks

| Item | Result |
| --- | --- |
| Symbol and schematic | All sixteen names, electrical roles and net assignments match ams DS001047 v4-00 Figures 3/4. The project symbol and embedded schematic definition agree. |
| Footprint | All sixteen native/library land centers independently match Figure 59 after converting its bottom-view contact drawing to top view. Body is nominally 2.60 × 3.65 × 1.09 mm. No center exposed pad is specified or added. |
| Supplies and bypass | Pins 3/10 share 3.3 V, within the 2.7–3.6 V operating range. C23 and C14 are separate 100 nF CL05B104KO5NNNC C1525 parts on the front. Supply-pad center distances to the nearer bypass are 1.3995 mm for VDDA/C23 and 1.1941 mm for VDDD/C14. These are geometry checks, not measured loop impedance. |
| Reference | Pin 4 connects only to R27's reference end. R27 returns to GND and is MCU0805MD3304BP500 C4313228, 3.3 MΩ ±0.1% ±25 ppm/K, meeting the specified 3.3 MΩ ±1%, ≤50 ppm/K requirement. |
| Ground and interfaces | Analog ground pins 1/2/5/6/15/16 and digital pin 11 return to GND. A0/A1 are grounded for address 0x74. SDA/SCL are pins 12/13, with one external 4.7 kΩ pull-up on each line. SYN is held low for internally timed command mode. READY is explicitly unconnected, not grounded. No external synchronization circuit or clock is required for that mode. |
| Connectivity | The current [electrical sweep](../v1_1_final_sweep_20261016/electrical/README.md) independently establishes no opens, parity errors, foreign-net copper overlaps or disconnected same-net pad groups. U6 and its supporting circuit are included in those full-board checks. |
| Population variant | The populated export has 58 references, 42 top/16 bottom, adding only U6 to the 57-reference pilot population. All retained BOM/CPL rows remain identical. Its front paste restores exactly sixteen U6 apertures. The [package proof](../v1_1_final_sweep_20261016/package-verification.json) covers the full geometry comparison. |
| Nearby via | One GND via's copper annulus intersects the maximum package-body projection at the lower-left edge. Its center is (72.771,39.243) mm, outside that projection; the 0.60/0.30 mm annulus/hole is tented on both faces. It has no U6 paste aperture. This is not an unpadded exposed-center connection. Preserve the exported tenting. |

The 300 ns I²C rise/fall limit applies even when firmware uses a 100 kHz clock. The retained [digital review](../v1_1_peer_review_20261014/digital/README.md) already bounds the capacitance uncertainty; it does not justify replacing the pull-ups with weaker resistors. There is no new wiring correction indicated by this closeout. An assembled waveform is a board bring-up measurement, not a missing schematic review.

## Exact U6 assembly target

- Manufacturer: ams OSRAM. Current BOM identity: **AS7331-AQFM**, LCSC **C20482877**. The primary ordering table lists **AS7331-AQFT** as the same OLGA16 device and marking with 5,000 rather than 1,000 parts per reel. It is electrically and mechanically compatible. If AQFT is what JLC actually obtains, record that exact identity in a newly generated assembly BOM before use; do not silently relabel stock or treat a quoted MOQ as guaranteed.
- Place on the **front/top**. Center in native PCB coordinates: **(74.250,37.490) mm**. Exported CPL center: **(74.250,-37.490) mm**, because its Y axis is reversed. The current native/CPL angle is **180°**.
- Viewed from the component side with the board top upwards, **pin 1 and the package dot must be lower-right**. Native pad 1 center is **(75.000,39.065) mm**; in CPL axes this is **(75.000,-39.065) mm**. Pin 1 is GND. Do not mirror the device.
- The [placement guide](uv-placement-guide.svg) is the physical reference. A supplier may use a different numerical angle for its library model; its final machine placement must meet this pin-1 target. This coordinate/geometry review is complete now. JLC's library-specific mapping is information only JLC can provide, not unfinished CAD work.

## Process specification to give JLC with the sourcing inquiry

The manufacturer publishes package contacts but no recommended PCB land/stencil pattern. The reviewed engineering pattern uses **0.35 mm square copper lands and 0.30 mm square paste apertures on 0.50 mm row pitch**, with no center aperture. Use **100 µm stencil thickness as the requested process** and **no additional blanket paste reduction**. The square aperture area/wall-area ratio is 0.75 at 100 µm; it falls to 0.625 at 120 µm. JLC must accept this optical LGA process or propose its concrete correction before adding U6. The full populated package is already generated; no layout work is waiting for that answer.

Apply DS001047 v4-00 printed pages 67–69:

- **MSL3**: preserve moisture-barrier packaging, desiccant and humidity history; floor life **168 h at <30 °C/<60% RH**. Unopened shelf life is **24 months at <40 °C/<90% RH**. If those limits or the moisture indicator fail, the specified rebake is **50 °C for 12 h**. Do not substitute a routine high-temperature bake.
- Reflow: average preheat gradient **2.5 °C/s**, soak **2–3 min**, at most **60 s above 217 °C**, **50 s above 230 °C**, and **10 s above peak minus 10 °C**; **260 °C peak**, cooling limited to the stated **5 °C/s** magnitude. JLC must account for U6 in its double-sided sequence. The primary document does not state a maximum reflow-pass count, so one must not be invented.
- Keep the optical aperture free of flux, paste, solder, glue, tape and coatings; do not bear a placement nozzle on the optical aperture. Follow the manufacturer's neutral-cleaner guidance, including IPA, and avoid acidic/alkaline chemistry. The current cart's generic no-clean option alone does not prove an optical aperture stays clean: JLC must accept an optical-safe flux/handling process for the populated variant.
- Use ESD-controlled handling appropriate to **750 V HBM / 500 V CDM** ratings. Retain all sixteen stencil openings for a populated U6; the UV-omitted stencil is not interchangeable.

The nozzle instruction is an engineering handling requirement to preserve the optical opening; it is not a claimed manufacturer nozzle specification. JLC supplies its actual nozzle, paste, stencil and double-sided process. Those items belong in the same sourcing/process reply as quantity, price and dispatch, so there is no separate internal “review later” placeholder.

## What the one supplier reply must settle

1. Exact genuine order code, accepted tape/MSL format, required quantity including attrition, all costs and earliest finished-board dispatch.
2. Acceptance of the physical pin-1 target above and its mapping to JLC's actual part library or machine program.
3. Acceptance of the stated stencil, reflow, moisture and optical handling requirements, or a specific proposed process change.

If the response supports acceptable cost/timing and the unchanged target, the remaining action is a controlled supplier population update using the prepared full-UV package. If JLC supplies a different suffix or proposes a machine-angle adjustment, update that exact assembly identity/convention and verify the resulting imported row. That response-dependent execution cannot truthfully be marked complete before there is a source/model to import. It does not require reopening the PCB layout review.

Firmware bring-up, actual sleep current, optical calibration and cold flight behavior require assembled hardware. They are development/flight qualification, separate from the pre-order hardware review. AS7331 starts in power-down after power-on/software reset; populating it does not automatically create a continuous 2 mA load. A populated flight image still needs the dedicated command-mode driver and measured behavior. Neither assembly nor this review certifies an ozone measurement.

Primary sources re-read for this closeout: [AS7331 datasheet DS001047 v4-00](../v1_1_release_20261012/as7331/review/as7331-datasheet-v4-00.pdf), printed pp6–10, 15, 23–24, 44, 63–69, with pin/package figures visually inspected; [PD001048 v2-00 design guidelines](../v1_1_release_20261012/as7331/review/design-guidelines.pdf); [Vishay resistor specification](../v1_1_release_20261012/as7331/review/vishay-mcx-resistors.pdf). Datasheet SHA-256: `60c13168a4012c1642277b8d8f9557e6f835c3b9efbfd7cc086be25c5a4c670a`.
