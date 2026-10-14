# RF peer review, 2026-10-14

**Initial audit verdict: the GNSS RF/power placement needed a coordinated revision before claiming a properly referenced RF feed. The exploratory west detour was rejected. This initial audit made no CAD or Git changes.**

A subsequent isolated, bounded placement revision is described in [left-feed-review.md](left-feed-review.md). Its current review status and eventual frozen hashes are authoritative for that candidate; the source measurements below remain historical evidence against the original AS7331 board. Adding more ground vias alone cannot repair the occupied opposite-layer reference under the feed. The LoRa feed does not cross either converter switch node.

## Evidence boundary

Exact PCB: `hardware/pcb/stratolink.kicad_pcb`, SHA-256 `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`. Geometry is extracted from its saved native fills without refilling or saving. This is the promoted AS7331 board. The current local project has separately changed mask rules; no conclusions here depend on those relaxed rules. Any future candidate must use the strict project in the reviewed `review/hardware-v1.1` worktree.

`native-rf-geometry.json` contains pads, track/via copper, saved filled zones, nominal stackup and footprint body graphics. Native curved-copper approximation requests a maximum 2 µm error. It does not include board text or graphic copper. Therefore the exploratory clearance screen is incomplete and must not be interpreted as DRC approval. In particular the west detour also enters the vicinity of copper branding. `route-comparison.json` records the quantitative projection comparison; `compare_routes.py` reproduces it. No electromagnetic, loss, C/N0 or impedance measurement was made.

## Verified problems and non-problems

| Item | Native evidence | Consequence |
|---|---|---|
| GNSS feed crosses boost switching copper | `Net-(AE2-A)` is 0.75 mm F.Cu at x=62.882; `Net-(U1-LBOOST)` is 0.35 mm B.Cu at y=40.769. They cross at **(62.882,40.769) mm**. | The two copper features directly oppose one another through the nominal 0.31 mm dielectric. There is no intervening reference plane on this two-layer PCB. Actual coupled noise requires measurement; this geometry is an avoidable risk. |
| GNSS RF_IN opposes capacitor positive copper | U3.11 is centered at **(60.787001,45.114001)** F.Cu. C5.1 `/VBAT` rear land occupies **x60.125…62.625, y44.457…47.957 mm**. | The reference plane is already absent at the receiver launch. Rerouting farther away cannot fix that launch without placement changes. |
| Original main feed is not continuously backed by GND | Main path is **13.439242 mm**, excluding the ESD spur. Its centerline lacks directly projected saved rear GND over **8.012974 mm**. This diagnostic includes terminal regions and is not an impedance model. | Existing front coplanar GND and nine GND vias within 1 mm copper-edge distance do not establish a continuous rear RF return. The original design already has ground on both sides; the issue is its geometry and interruptions. |
| LoRa does not cross the converters | `Net-(AE1-A)`, U2.12 to AE1.1 near y79.6…82.7. Minimum projected copper-edge distance to LBOOST is **38.156 mm**, to LBUCK **37.020 mm**. | Do not attribute the GNSS crossing to both antennas. LoRa still needs its own impedance/return assessment and assembled antenna tuning. |

The four original GNSS main-route object UUIDs are recorded in `route-comparison.json`. The existing diode branch was excluded from the main-feed length. The direct switch crossing and capacitor-pad overlap predate the AS7331 integration.

## Rejected west detour

The clearance exploration produced a manually simplified **19.068644 mm** path, **41.89% longer** than the original. The point list is in `route-comparison.json`. This is a polyline screening sketch, not a finished route: it was not radiused, refilled, run through native DRC or put into a native candidate.

It removes the direct boost crossing but introduces these tradeoffs:

- The trace projection crosses rear **U8.4 `/SC_BAL_OUT`, U8.5 `/VBAT`, R25.1 `/SC_HALF_REF`, C22.1 `/VBAT`**, and still part of C5.1. These are not ground-reference surfaces.
- Against the original saved rear fill, **15.754592/19.068644 mm** of centerline lacks directly underlying rear GND. This is a baseline projection screen, not a prediction of a new fill. Opposing component lands would remain even after a refill.
- It needs an additional `/SC_MID` crossover onto B.Cu and a new 0.5/0.3 mm via, further interrupting the rear reference. It also conflicts with the old front ground chain and GND vias at **(58.625,41.708)** and **(57.632,40.68)**.
- Copper branding was not included in the automated clearance geometry and is another unresolved obstacle.

These costs defeat the premise of a small, clearly beneficial RF repair. The digital reviewer independently reproduced the rear-pad overlaps and saved-ground projection. **Do not promote this detour or the A* grid output.** No switching traces or footprints were moved.

## Concrete placement revision requirements

1. **Co-design the RF launch and capacitor terminals first.** Reserve a ground-backed launch at U3.11 (60.787001,45.114001), moving the C5 positive terminal or the GNSS module/antenna location as a coordinated layout change. Preserve the preferred rear capacitor body envelope where possible, but do not treat its current lead position as immutable if it prevents the RF reference.
2. **Reserve one short corridor from that launch to AE2.1 (62.882,33.218), or relocate AE2 with the module.** Both the rear copper under it and nearby return must be GND. The present crossing at (62.882,40.769) must disappear through converter/module placement, not an enlarged loop of switching copper around the receiver. L1 is centered at (60.103,38.1865) on the rear; moving it alone to the right collides with the tightly grouped power components. A usable change therefore includes the converter group or RF placement rather than a lone trace jog.
3. **Keep the RF side facing the antenna and digital side facing digital circuitry.** The current RF_IN escape initially runs rightward under the module before turning upward. A direct outward launch is preferable when placement is reconsidered. Keep ESD geometry short, with a direct nearby return, and evaluate its capacitance within the matching network.
4. **After the corridor exists, size a 50 Ω grounded coplanar line against the actual JLC stackup.** The nominal PCB file declares 0.035 mm copper, 0.31 mm FR4 (εr=4.5) and 0.01 mm mask on each face, total 0.4 mm. Obtain the fabrication dielectric/copper tolerances, select trace width and front GND gap together, and retain an uninterrupted rear reference. The inherited 0.75 mm width alone is not evidence of 50 Ω. Mask and nearby ground change the impedance; a microstrip-only formula cannot qualify this layout.
5. **Then add short-return stitching and review every island.** Both-face GND is useful around the PCB feed and under the receiver. Stitch copper tongues rather than leaving floating ends; preserve DC connectivity and bypass return paths. Extra vias cannot replace missing rear copper beneath signal/component lands. Keep any fabrication-neck fix away from the RF corridor and switching node.

These are explicit placement constraints, not unverified replacement coordinates or a ready-to-fabricate proposal. They require a fresh native DRC/connectivity review and source-equivalent netlist check after routing. Use rounded bends or consistent 45° transitions with adequate corner clearance; do not transfer a grid staircase, acute junction or small copper pocket into the board.

## Antenna and validation boundary

AE1 and AE2 are soldered straight enameled-wire radiators, not spring antennas despite old footprint history: current native values are **82 mm LoRa** and **48 mm GNSS L1**. The on-board routes from module RF pin to wire hole are transmission lines; the off-board wires, panel mounts, suspension and entire board return form the antenna environment. “Put ground on both sides” applies to the feed/reference design, not to covering the radiating wire with ground.

Use assembled geometry for VNA measurements of matching and isolation. Compare GNSS C/N0/acquisition under controlled weak signal with the harvester switching/quiet, representative solar input, and LoRa idle/transmitting; compare against the flown layout. Keep GNSS supply filtering/decoupling findings from the power review in scope: a better RF route alone cannot qualify receiver power or coexistence. DRC and a 50 Ω line calculation cannot prove the antenna match, electromagnetic coupling, radiation performance or flight improvement.

## Primary guidance used

- [u-blox MAX-M10S Integration Manual, UBX-20053088 R05, pp. 80–81](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf): short RF connection, separate noisy/digital circuitry, grounded coplanar line with solid reference below, stackup-derived 50 Ω geometry, and terminated GND tongues. Cached text: `analysis/redesign_20261010/metrology/sources/MAX-M10S-integration.txt`, lines 3928–3984.
- [RAK3172 datasheet, RF interface/layout guidance](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/): avoid switching-node interference, use 50 Ω traces, direct ground returns and curved routing. Cached text: `analysis/redesign_20261010/radio_mechanics/sources/rak3172_browser.txt`, lines 398–410.

Reproduction: run `extract_rf.py` with KiCad's bundled Python/wx against the exact source hash, then `analysis/.venv/bin/python analysis/v1_1_peer_review_20261014/rf/compare_routes.py`. `plot_rf.py` creates the two-layer upper-board copper overview. `route_screen.py` and its output are retained only as **rejected exploratory evidence**; they are not a routing recipe.
