# v1.1 hardware review

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. Current PCB SHA-256: `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13`.

This revision adopts the engineer-rerouted board. The circuit is unchanged. Local repairs remove two shorts, reconnect two ground sections, correct mask clearances and two copper pockets, and move only C5 by 1.30 mm to restore ground beneath the GNSS input. All other 67 footprint poses are retained from the supplied board. The upward GNSS antenna, side solar mounts and rear capacitor remain.

- [Final adversarial sweep and current source proofs](../../analysis/v1_1_final_sweep_20261016/README.md)
- [Engineer reroute and earlier bounded fixes](../../analysis/v1_1_engineer_review_20261015/README.md)
- [KiCad project and parts library downloads](../downloads/README.md)
- [Front](../../analysis/v1_1_final_sweep_20261016/mechanical/visual/top.png), [rear](../../analysis/v1_1_final_sweep_20261016/mechanical/visual/bottom.png) and [full assembly](../../analysis/v1_1_final_sweep_20261016/mechanical/visual/assembly.png) renders
- [Fabrication and manual assembly instructions](FABRICATION.md)
- [Current Gerbers, BOM and verified placement file](../gerbers/v1.1-final-20261016/README.md)
- [Saved JLC Y26 draft and supplier review](SUPPLIER_REVIEW.md)
- [Remaining pilot work and v2 checklist](TODO.md)

Strict native checks report zero DRC violations, opens, schematic mismatches or unexcluded ERC findings. Two documented ERC exclusions remain. Independent review checks the logical circuit, 259 physical pads, filled-copper connectivity, mask openings, 68 local footprints and 63 model attachments. The reports quantify remaining open copper wedges and decorative microdetail for supplier review. RF impedance, noise, cold behavior and mechanical strength require physical qualification.

U6 is AS7331 in the full CAD but is omitted from the initial three assemblies; C14/C23/R27 stay fitted. The pilot stencil removes only U6's 16 apertures. Renders show full CAD population. Use the UV-DNP firmware target for these pilots.

JLC Y26 is saved for five boards and three assemblies. The displayed subtotal is $355.22 with DHL shipping and the current coupon, excluding possible factory-review extras. The current estimate is October 20 dispatch followed by 2–4 business days shipping; timing is not guaranteed. All 57 unique selected parts and seven populated IC orientations have been checked. Construction remains 0.40 mm FR4, green mask, no silkscreen and ENIG. Factory CAM and final user approval remain pending; nothing has been ordered.

The final sweep restored an accidentally deleted VSTOR voltage-sense segment in the working copy and restored strict mask rules. Current manufacturing geometry matches the previously uploaded files. Schematic cosmetics and five hidden fabrication fields are preserved. Both complete download archives were rebuilt and verified. A sourcing inquiry has been sent for AS7331 cost and earliest delivery, with the October 22 launch and subsequent development timing explained. A populated-UV package is prepared conditionally, but requires exact sourcing and U6 supplier orientation/process review before use.

This branch includes the scoped hardware changes in separate commits. [review-commits.json](review-commits.json) maps canonical hardware commits to this review branch. Unrelated local firmware and website work is excluded. Historical analysis retains its original source identities. The published project uses strict settings; unrelated local firmware, website and editor work remains separate.

From this checkout, verify the exact published sources, manufacturing outputs and review evidence:

```sh
python3 hardware/pcb/verify_review_package.py
python3 hardware/downloads/build.py --check
python3 analysis/v1_1_final_sweep_20261016/verify.py
```

These verify recorded artifacts. They do not rerun KiCad, supplier CAM or physical measurements.
