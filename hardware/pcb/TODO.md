# Stratolink v1.1 and v2 checklist

Updated 16 October 2026 after the final pre-order closeout. The [final sweep](../../analysis/v1_1_final_sweep_20261016/README.md) binds the current source and manufacturing files; the [pre-order closeout](../../analysis/v1_1_preorder_closeout_20261016/README.md) distinguishes completed preparation from later factory and pilot acceptance. JLC **Y26** is saved for five PCBs and three assemblies. The current external wait is the emailed AS7331 sourcing/lead-time quote. No checkout or payment has been made.

## Completed preparation for the three pilot assemblies

- [x] Compare the schematic, exported netlist and all physical pad assignments against the previous v1.1. No circuit changes.
- [x] Preserve the rerouted layout. Correct two signal-to-ground shorts, reconnect two ground sections, adjust local mask openings and remove two trapped copper gaps.
- [x] Move only C5, 1.30 mm downward, to restore rear ground beneath the GNSS input. Preserve the upward 48 mm antenna and the engineer's signal route.
- [x] Retain the improved C10 bypass placement. It is now 2.87 mm from U3 VCC. Measure rail behavior and FB1 voltage drop on pilots.
- [x] Run strict native DRC/ERC, schematic parity, independent filled-copper connectivity, mask, mechanical and 3D/library checks. See current evidence for exact source hashes and limitations.
- [x] Retain the green mask/no-silkscreen finish, 0.40 mm ENIG construction, solar notches, reinforced suspension holes, larger rear programming lands, corrected TMP117, microphone omission and flat rear capacitor.
- [x] Retain the full AS7331 circuit. Initial pilot omits only U6; C14/C23/R27 remain fitted. Use the explicit UV-DNP firmware target.
- [x] Regenerate and verify matching manufacturing and downloadable KiCad/library bundles from the final source.
- [x] Import and review both faces in JLC. All 57 selected references match exact MPN/LCSC/footprint/side data. All seven populated IC orientations have been reviewed; U8 uses verified supplier CPL 90 degrees. The current Y26 cart retains these files and selections.
- [x] Restore the missing working-copy VSTOR voltage-sense segment and strict mask checks; preserve schematic cosmetics and all reviewed footprint poses.
- [x] Prepare both UV-omitted and populated exports from the same current source. Verify U6 is the only population difference and sixteen U6 paste apertures are the only stencil difference.
- [x] Send JLC the sourcing inquiry with the current draft reference, total added cost, earliest dispatch and optical-package handling questions. Reply is expected in the personal email thread.

## Current external wait

- [ ] Receive JLC's AS7331 sourcing cost and lead-time reply, then choose the pilot population. Exact source/ordering identity and U6 supplier machine orientation/process acceptance belong to this supplier decision; the native U6 circuit, footprint and export are already prepared and reviewed. Keep the existing UV-omitted cart while awaiting that reply.

## Factory work after the ordering decision

These are checks of files JLC generates for the order, not unfinished native design work.

- [ ] Review JLC's production panel, rail/tab positions, fine-pitch mask/land handling, stencil and final placement output when they are issued. Preserve the notches, suspension holes, no-silkscreen finish and specified apertures. Check 57 unique placements for UV omitted or 58 for UV populated.
- [x] Manual production-file and placement confirmation enabled; automatic production approval disabled, verified again in the saved form. Preserve these settings when ordering and compare any supplier substitution or geometry change to the reviewed files.

Previous implementation decisions and their original evidence remain under [the v1.1 release record](../../analysis/v1_1_release_20261012/), [digital review](../../analysis/v1_1_peer_review_20261014/digital/README.md) and [power review](../../analysis/v1_1_peer_review_20261014/power/README.md). Retain both 10 uF capacitors, the 4.7 kohm I2C pull-ups and the established RAK SWD mapping. UART observation requires avoiding transmitter contention. These electrical decisions survive the reroute; old coordinates, mask results and supplier previews do not.

## Physical acceptance after the assembled pilots arrive

These require actual hardware and do not block ordering development samples. They remain required before calling the revision flight-qualified or ordering the larger batch. Follow the [pilot acceptance procedure](../../analysis/v1_1_release_20261012/pilot-acceptance.md), recording conditions, measured values and pass/fail evidence. None of these is completed by DRC or a model.

- [ ] **Inspect before power.** Verify green mask, exposed soldering lands, absent silkscreen, handling, fine-pitch joints/shorts, exact identities, orientation and connectivity. Confirm the chosen U6 population and C14/C23/R27 fitted. Hand-fit the flat capacitor after cleaning and check all three terminals.
- [ ] **Establish solar and storage bounds.** Measure cold panel Voc/I–V and BQ25570 input voltage/power. Measure charge plateau, both cells, midpoint startup/stability, cold ESR/leakage and load transients. Resolve charging faults and large steps before accepting the balancing circuit.
- [ ] **Verify dark endurance and sunrise recovery.** Use actual temperature and final assembly without debugger power. Measure residual GNSS current, brownout/reset and data recovery; nominal capacitor energy is not an all-night reserve.
- [ ] **Verify sensors and the pilot firmware.** Prove direct TMP117 ACK/ID/readings at 0x48 against a temperature reference. Confirm pressure, IMU, GNSS and unavailable UV/lux/acoustic reporting. Pressure fallback does not establish TMP117 operation. DNP firmware must issue no optical probes; a populated U6 needs its compatible driver and bring-up.
- [ ] **Qualify mounts and bridle.** Measure panel terminal thickness/wettable area, wire gauge, string material/diameter, apex height and total mass. Compare flex, rim wear and security with v1 under measured loads and cold/handling cycles; use sacrificial samples for uneven/out-of-plane loading.
- [ ] **Compare installed RF and GNSS behavior.** Record regional wire cut, exit and whole-payload geometry; compare orientation-dependent links, C/N₀, fix recovery and LoRa interference against v1. The new UV circuit warrants a matched full-assembly comparison even on DNP pilots. VNA match alone is insufficient. Follow the [matched whole-payload GNSS comparison](../../analysis/v1_1_top_gnss_20261014/reception-test.md); a top wire and higher satellite count do not by themselves prove better accuracy.
- [ ] **Accept the three pilots before a larger batch.** Review failures, rework, measured margins and sustainable component supply before ordering approximately fifteen.

## Follow-on experiments and supply work

- [ ] **Bring up AS7331 if populated.** Native hardware and both export options are complete; supply is the current external wait above. Validate bounded command-mode acquisition, verified power-down and raw multiband telemetry on the fitted part. Do not reuse DNP firmware after fitting U6; AS7331 provides no visible ALS.
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
