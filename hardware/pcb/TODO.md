# Stratolink v1.1 and v2 checklist

Updated 15 October 2026 for the engineer-rerouted board. The authoritative layout is the supplied review ZIP plus the small corrections recorded in the [current review](../../analysis/v1_1_engineer_review_20261015/README.md). Earlier layout and supplier records are historical. The saved JLC Y24 cart is stale. Plan five PCBs and three assembled pilots, followed by physical qualification before approximately fifteen payloads. Checkout/payment is not authorized.

## Current v1.1 review

- [x] Compare the schematic, exported netlist and all physical pad assignments against the previous v1.1. No circuit changes.
- [x] Preserve the rerouted layout. Correct two signal-to-ground shorts, reconnect two ground sections, adjust local mask openings and remove two trapped copper gaps.
- [x] Move only C5, 1.30 mm downward, to restore rear ground beneath the GNSS input. Preserve the upward 48 mm antenna and the engineer's signal route.
- [x] Retain the improved C10 bypass placement. It is now 2.87 mm from U3 VCC. Measure rail behavior and FB1 voltage drop on pilots.
- [x] Run strict native DRC/ERC, schematic parity, independent filled-copper connectivity, mask, mechanical and 3D/library checks. See current evidence for exact source hashes and limitations.
- [x] Retain the green mask/no-silkscreen finish, 0.40 mm ENIG construction, solar notches, reinforced suspension holes, larger rear programming lands, corrected TMP117, microphone omission and flat rear capacitor.
- [x] Retain the full AS7331 circuit. Initial pilot omits only U6; C14/C23/R27 remain fitted. Use the explicit UV-DNP firmware target.
- [x] Regenerate and verify matching manufacturing and downloadable KiCad/library bundles from the final source.
- [ ] Reimport current files into JLC and check every placement on both faces. U1 rotated and U8 moved to the front, so previous supplier rotation approval does not apply. See the [draft placement review](../../analysis/v1_1_engineer_review_20261015/manufacturing/rotation-review.md).
- [ ] Obtain factory CAM disposition for thin-board handling, rails/tabs, fine-pitch lands, solder mask, residual copper-artwork details and open solar notches. Native DRC is not factory approval.
- [ ] Review installed RF impedance, converter return-path noise and GNSS/radio coexistence experimentally. The 0.75 mm feed has a ground reference but is not qualified as a uniform 50 ohm line.

Previous implementation decisions and their original evidence remain under [the v1.1 release record](../../analysis/v1_1_release_20261012/), [digital review](../../analysis/v1_1_peer_review_20261014/digital/README.md) and [power review](../../analysis/v1_1_peer_review_20261014/power/README.md). Retain both 10 uF capacitors, the 4.7 kohm I2C pull-ups and the established RAK SWD mapping. UART observation requires avoiding transmitter contention. These electrical decisions survive the reroute; old coordinates, mask results and supplier previews do not.

## Physical pilot acceptance

Follow the [pilot acceptance procedure](../../analysis/v1_1_release_20261012/pilot-acceptance.md), recording conditions, measured values and pass/fail evidence. None of these is completed by DRC or a model.

- [ ] **Inspect before power.** Verify green mask, exposed soldering lands, absent silkscreen, handling, fine-pitch joints/shorts, exact identities, orientation and connectivity. Confirm U6 absent and C14/C23/R27 fitted. Hand-fit the flat capacitor after cleaning and check all three terminals.
- [ ] **Establish solar and storage bounds.** Measure cold panel Voc/I–V and BQ25570 input voltage/power. Measure charge plateau, both cells, midpoint startup/stability, cold ESR/leakage and load transients. Resolve charging faults and large steps before accepting the balancing circuit.
- [ ] **Verify dark endurance and sunrise recovery.** Use actual temperature and final assembly without debugger power. Measure residual GNSS current, brownout/reset and data recovery; nominal capacitor energy is not an all-night reserve.
- [ ] **Verify sensors and the pilot firmware.** Prove direct TMP117 ACK/ID/readings at 0x48 against a temperature reference. Confirm pressure, IMU, GNSS and unavailable UV/lux/acoustic reporting. Pressure fallback does not establish TMP117 operation. DNP firmware must issue no optical probes.
- [ ] **Qualify mounts and bridle.** Measure panel terminal thickness/wettable area, wire gauge, string material/diameter, apex height and total mass. Compare flex, rim wear and security with v1 under measured loads and cold/handling cycles; use sacrificial samples for uneven/out-of-plane loading.
- [ ] **Compare installed RF and GNSS behavior.** Record regional wire cut, exit and whole-payload geometry; compare orientation-dependent links, C/N₀, fix recovery and LoRa interference against v1. The new UV circuit warrants a matched full-assembly comparison even on DNP pilots. VNA match alone is insufficient. Follow the [matched whole-payload GNSS comparison](../../analysis/v1_1_top_gnss_20261014/reception-test.md); a top wire and higher satellite count do not by themselves prove better accuracy.
- [ ] **Accept the three pilots before a larger batch.** Review failures, rework, measured margins and sustainable component supply before ordering approximately fifteen.

## Deferred v1.1 experiments and supply work

- [ ] **Source and bring up populated AS7331 boards.** Current shortage does not change the chosen complete circuit. Obtain the exact part through a verified route, review its own placement/stencil/MSL process, implement bounded command-mode acquisition and verified power-down, and version raw multiband telemetry. Do not reuse DNP firmware after fitting U6; AS7331 provides no visible ALS.
- [ ] **Characterize the UV experiment.** Measure dark offsets, gain/exposure, saturation, temperature, angular response and sunlight VIS/NIR leakage. Design an appropriate opaque angle-limiting collector and blocking filter as needed, then compare against calibrated spectra. Broad-band ratio alone is not accepted ozone metrology. [Requirements](../../analysis/v1_1_release_20261012/as7331/review/requirements.md).
- [ ] **Find a sustainable flat-capacitor replacement.** Preserve the current 30 × 14 × 3.7 mm rear envelope unless measurements justify a change. Compare price/stock, terminals, mass, tolerance, cold ESR/leakage and dark/recovery performance. Smaller 470 mF and wider HW203F candidates are tradeoffs, not equivalents. Local notes: `analysis/v1_1_layout_20261012/flat_storage/README.md`.
- [ ] **Resolve IMU idle current.** Verify LIS2DH12 SA0 pull-up control (`CTRL_REG0.SDO_PU_DISC`) in the selected firmware. The remaining grounded-strap ERC disposition does not establish minimum sleep current. The old LTR390 interrupt configuration no longer applies to this PCB.
- [ ] **Evaluate GNSS upgrades against measured benefit.** Keep MAX-M10S as baseline. Recheck exact MAX-M11N availability/firmware, pins 16/17 and true power isolation before raw-carrier work. Compare MAX-M10N navigation/coexistence with matched antennas and local radio activity. PPS/reset does not isolate power. Local notes: `analysis/v1_1_layout_20261012/gnss_uv/README.md`.
- [ ] **Qualify one-radio regional, wildlife and Meshtastic operation.** Measure the exact front end, antenna and compatible channel/preset windows. Regional labels do not prove 433 MHz sensitivity, and a wire change cannot bypass internal matching. One receiver cannot listen on all channels simultaneously. Local notes: `analysis/redesign_20261010/radio_mechanics/README.md`.

## v2 investigations

- [ ] **Repack a shorter, possibly thicker board.** Existing modeling adds about 0.50 g at 0.6 mm for the same outline. Equal mass needs about 40.9 mm length at current width under proportional copper scaling; retained envelopes span over 52 mm. Produce an actual fit before claiming parity; compare upper mounts, center of mass and RF. [Materials model](../../analysis/v1_1_solar_attachments_20261012/materials/README.md).
- [ ] **Improve ambient-air temperature measurement.** Test shielding, thermal isolation or a lightweight remote probe against references; separate chip accuracy from solar/conduction/low-pressure error.
- [ ] **Specify an identifiable atmospheric GNSS experiment.** Choose raw satellite observations or a separate coherent payload-to-ground instrument, with appropriate antennas, logging, clocks and references. Accurate position plus LoRa timestamps does not separately identify path temperature, pressure and humidity. Local notes: `analysis/redesign_20261010/metrology/README.md`.
- [ ] **Develop ozone optics from reference data.** Compare broad bands against narrower simultaneous absorption/reference bands or a spectrometer, including out-of-band leakage, pointing, clouds and aerosols. Validate column above the balloon, not local concentration.
- [ ] **Revise RF/power architecture only for measured needs.** A second receiver needs a demonstrated service benefit with acceptable mass/power/cost. Add true GNSS isolation, logging and qualified solar/storage when experiments define requirements.

Historical analysis retains intermediate states. Local working notes may sit outside the scoped release checkpoint; the final manufacturing package must remain reproducible from its own manifest.
