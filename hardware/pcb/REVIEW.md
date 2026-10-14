# v1.1 hardware review

Open [stratolink.kicad_pro](stratolink.kicad_pro) in KiCad 10. The schematic, board, project-local libraries and 3D models are included. Current PCB SHA-256: `88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`.

- [Changes from the flown board](../../analysis/v1_1_release_20261012/manual-review-changes.md)
- [Latest peer review and decisions](../../analysis/v1_1_top_gnss_20261014/README.md)
- [GNSS feed, reference and placement](../../analysis/v1_1_top_gnss_20261014/rf/top-feed-review.md)
- [Assembly and fabrication details](FABRICATION.md)
- [Matching pilot Gerbers, BOM and placement file](../gerbers/v1.1-pilot/README.md)
- [Current front rendering](../../analysis/v1_1_top_gnss_20261014/native/visual/top.png)
- [Current rear rendering](../../analysis/v1_1_top_gnss_20261014/native/visual/bottom.png)

The latest revision restores the original top GNSS feed hole and upward 48 mm wire. L1 moves 0.50 mm right and D3 moves beside the rounded feed. The 16.9634 mm route goes west of L1, avoiding its switching connection and retaining rear reference plus connected front ground on both sides. Upper solar and balancing/sense branches move accordingly. C1/C2/R2 thermals are preserved; R25.GND is solid under the reference. C5 retains its earlier 1.8 mm shift. PICO/STRATOLINK groups move 0.6/0.4 mm left without changing their shapes. C8/C21, the 4.7 kΩ pull-ups and the verified SWD pinout remain.

U6 is AS7331-AQFM with UVA/UVB/UVC channels. The full circuit is in CAD, but the initial three assemblies omit U6 and fit C14/C23/R27. The pilot stencil removes only U6's 16 apertures. Populated UV operation needs firmware and calibrated optics. Renders show the full CAD including U6.

Construction remains green solder mask, no silkscreen, 0.4 mm FR4 and ENIG. Strict native checks report zero DRC violations, open connections, schematic mismatches or unexcluded ERC findings, with two documented ERC exclusions. Independent review covers 259 physical pads, 250 logical connections, actual filled copper, ground reference, preserved thermals and unchanged project/library/model inputs. The copper review finds no substantive defects under its documented angle/pocket/island thresholds. Ten raw contour remnants are explicitly quantified at 0.36 to 4.51 nm rather than hidden. Neither those checks nor the idealized impedance calculation qualifies RF performance or thin-board strength.

The [assembled view](../../analysis/v1_1_top_gnss_20261014/native/visual/assembly.png) shows the top wire and side panels. The nominal minimum solar separation is 21.58 mm; actual suspension-line clearance needs checking through motion.

Engineering follow-ups include the remote C10 GNSS bypass, FB1 resistance, measured 300 ns I²C rise time, supply transients and assembled antenna behavior. Factory CAM and physical pilot tests remain pending. The saved JLC Y24 cart contains the earlier revision and must be reimported and reviewed before ordering.

This branch starts at main commit `ba3a0e8` and retains the v1.1 changes in separate commits. [review-commits.json](review-commits.json) maps the canonical hardware commits to this branch. Unrelated local firmware and website edits are excluded. Historical reports retain their original source hashes, paths and commit IDs; intermediate and rejected layouts are not the current release. The strict published project retains stronger mask checks than the canonical editor's preserved local overrides.

From the repository root, verify the published CAD, outputs and source-bound evidence without KiCad:

```sh
python3 hardware/pcb/verify_review_package.py
```

Native inspection still requires KiCad. Older analysis scripts may require substituting a local path or a mapped commit. The portable verifier checks the published artifacts and recorded evidence; it does not rerun physical or RF measurements.
