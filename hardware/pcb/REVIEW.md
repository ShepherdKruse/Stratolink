# v1.1 hardware review

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. Current PCB SHA-256: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`.

This revision adopts the engineer-rerouted board. The circuit is unchanged. Local repairs remove two shorts, reconnect two ground sections, correct mask clearances and two copper pockets, and move only C5 by 1.30 mm to restore ground beneath the GNSS input. All other 67 footprint poses are retained from the supplied board. The upward GNSS antenna, side solar mounts and rear capacitor remain.

- [Full review and exact change list](../../analysis/v1_1_engineer_review_20261015/README.md)
- [KiCad project and parts library downloads](../downloads/README.md)
- [Front](../../analysis/v1_1_engineer_review_20261015/mechanics/visual/top.png), [rear](../../analysis/v1_1_engineer_review_20261015/mechanics/visual/bottom.png) and [full assembly](../../analysis/v1_1_engineer_review_20261015/mechanics/visual/assembly.png) renders
- [Fabrication and manual assembly instructions](FABRICATION.md)
- [Current Gerbers, BOM and verified placement file](../gerbers/v1.1-pilot-supplier-20261016/README.md)
- [Saved JLC Y25 draft and supplier review](SUPPLIER_REVIEW.md)
- [Remaining pilot work and v2 checklist](TODO.md)

Strict native checks report zero DRC violations, opens, schematic mismatches or unexcluded ERC findings. Two documented ERC exclusions remain. Independent review checks the logical circuit, 259 physical pads, filled-copper connectivity, mask openings, 68 local footprints and 63 model attachments. The reports quantify remaining open copper wedges and decorative microdetail for supplier review. RF impedance, noise, cold behavior and mechanical strength require physical qualification.

U6 is AS7331 in the full CAD but is omitted from the initial three assemblies; C14/C23/R27 stay fitted. The pilot stencil removes only U6's 16 apertures. Renders show full CAD population. Use the UV-DNP firmware target for these pilots.

JLC Y25 is saved for five boards and three assemblies at a quoted $332.63 before shipping, tax and manual-review adjustments. All 57 parts were selected and checked. Fresh previews confirmed all seven IC orientations after correcting U8 supplier rotation from 180 to 90 degrees. Native CAD is unchanged. Y24 was removed. Construction remains 0.40 mm FR4, green mask, no silkscreen and ENIG. Factory CAM and final user approval remain pending; nothing has been ordered.

This branch includes the scoped hardware changes in separate commits. [review-commits.json](review-commits.json) maps canonical hardware commits to this review branch. Unrelated local firmware and website work is excluded. Historical analysis retains its original source identities. The published project uses strict settings; pre-existing local editor overrides in the canonical checkout were preserved.

From this checkout, verify the exact published sources, manufacturing outputs and review evidence:

```sh
python3 hardware/pcb/verify_review_package.py
python3 hardware/downloads/build.py --check
python3 analysis/v1_1_supplier_review_20261016/verify.py
```

These verify recorded artifacts. They do not rerun KiCad, supplier CAM or physical measurements.
