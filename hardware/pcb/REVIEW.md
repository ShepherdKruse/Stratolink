# v1.1 hardware review

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. The schematic, board, local libraries and 3D models are included.

- [Changes from the flown board](../../analysis/v1_1_release_20261012/manual-review-changes.md)
- [Assembly and fabrication details](FABRICATION.md)
- [Independent electrical and layout review](../../analysis/v1_1_release_20261012/as7331/review/README.md)
- [Pilot Gerbers, BOM and placement file](../gerbers/v1.1-pilot/README.md)
- [Front rendering](../../analysis/v1_1_release_20261012/as7331/visual/final-green-full.png)
- [Rear rendering](../../analysis/v1_1_release_20261012/as7331/visual/final-green-bottom.png)

U6 is the AS7331-AQFM UVA/UVB/UVC sensor. The full circuit is in CAD. The initial three assemblies omit U6 and fit C14, C23 and R27. Populated UV operation needs firmware and optical calibration before attempting an ozone-column estimate.

The board uses green solder mask, no silkscreen, 0.4 mm FR-4 and ENIG. Native checks found zero DRC violations, open connections or schematic mismatches. ERC has zero unexcluded findings and two documented exclusions. Factory CAM approval and physical pilot tests remain pending.

This branch starts at main commit `ba3a0e8` and carries the 13 v1.1 commits separately. Existing firmware and website work from main is retained. The four firmware files changed by this branch support the revised pin map, microphone omission and UV-DNP pilot.

The CAD and manufacturing files match the reviewed local revision `8ce5f5e`. Historical reports retain their original branch names, workstation paths and commit IDs. [review-commits.json](review-commits.json) maps those 13 original commits to this branch. Older generation scripts may require substituting a mapped commit or a local path; the reports themselves are preserved. Archived draft reports describe intermediate designs, including the superseded bare-board finish. Use the files linked above for the current design.

From the repository root, verify the published CAD, package and final review evidence:

```sh
python3 hardware/pcb/verify_review_package.py
```
