# Independent microphone ECO review

**Pass for this ECO.** Reviewed against Git `38de8d750c476258ba217c76274216863cf0b29c` using native KiCad 10 netlist export, filled-board DRC and copper connectivity. This is a scoped regression review, not manufacturing release approval; inherited whole-board findings remain.

The final board removes exactly MK1, C13 and R20. The microphone's complete footprint is gone, including its 0.5 mm acoustic NPTH, explicit solder-mask/paste geometry and model. All 59 retained footprints remain identical except the intentional NC net/type fields on U2.31/PB4 and U2.32/PB3. Both pins are physically isolated. The corrected TMP117 symbol, footprint and copper connections are preserved.

Native connected-pad sets match the baseline for all **224 retained connected/other pads**, and all **217 retained schematic net nodes** match exactly. This checks real copper continuity, including FB1's shared 3.3 V feed across the former C13 pad, rather than merely comparing net names. There are zero board unconnected items. Four short GND segments added at U2.28 and R23.2 preserve satisfactory plane connections after removal of the long microphone signal tracks; existing non-microphone routes and retained component placements remain unchanged.

| Check | Before | After | Interpretation |
|---|---:|---:|---|
| Project-rule DRC findings | 78 | 73 | Two mic mask errors and three removed-footprint warnings eliminated; no added findings |
| Project-rule schematic parity | 11 | 11 | Identical inherited findings |
| Enabled 0.15 mm clearance screen | 92 | 87 | No new geometry defect; one existing collision reported against a different pad |
| Screen schematic parity | 11 | 11 | Identical inherited findings |
| Native unconnected count | 0 | 0 | All retained copper connectivity preserved |
| ERC findings | 56 | 55 | Removed mic library warning; existing shared-GND pin warning chooses a new endpoint |

The clearance screen's raw report changes from the VSTOR track versus R23.1 (0.133 mm) to that same track versus R23.2 (0.147 mm). Both complete pads and the complete VSTOR track are identical in baseline and final CAD. The R23.2 clearance is directly recoverable from unchanged geometry: the track's upper edge is at y = 66.101 mm and the pad's lower edge at y = 65.953998 mm, giving 0.147002 mm. This is a preexisting gap below the diagnostic 0.15 mm threshold, not a change caused by the new ground strap. The raw added/removed report entries remain visible in `drc-comparison.json` with this classification.

Similarly, ERC now compares U6.5's existing unspecified ground pin against C14.1 instead of the removed #PWR034 symbol. The independent before/after netlists confirm that both U6.5 and C14.1 were already on GND. No retained net connection changed. This report-selection change is preserved and explained in the comparison JSON.

The first removal/refill exposed new single-spoke plane connections at U2.28 and, under the stricter diagnostic settings, R23.2. Those were closed with explicit short ground connections and checked under both rule sets. Restoring the remote mic ground stitching did not resolve the U2 finding. The final change preserves pad properties, existing thermal rules and all retained net connectivity.

## Final canonical files

SHA-256:

```text
hardware/pcb/stratolink.kicad_pcb
4e132fcc1e80383b270402544700d7ff1f818680a222ba0ceed45e0c125a497f

hardware/pcb/stratolink.kicad_sch
f57249e54bf07e10ea75f4338c9807163fbd549f2123712b9805d14bd2a01cd1
```

`check_removal.py` bootstraps missing baseline CAD and netlist from the frozen Git commit, so the duplicate scratch CAD need not be committed. Run it with KiCad's bundled Python. It writes `comparison.json`. `check_drc_delta.py` compares the saved before/after reports, retains raw report differences and validates the explicitly documented representative-pair changes.

For the diagnostic screen, copy the frozen baseline and final CAD into separate scratch directories with basename `stratolink`; use `screen-settings.kicad_pro` as each copied project's settings and resolve the same footprint library. Run `kicad-cli pcb drc --format json --refill-zones --save-board --schematic-parity` on each scratch board. The enabled screen uses 0.15 mm minimum copper clearance, 0.20 mm copper-to-edge clearance, 0.10 mm track width, 0.10 mm via annulus, 0.30 mm through drill and two resolved thermal spokes. Canonical design rules were not weakened or changed. Final reports are `clearance_screen/{before,after}/drc.json`.
