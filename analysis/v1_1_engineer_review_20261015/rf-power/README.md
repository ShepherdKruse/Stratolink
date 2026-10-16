# RF and power review

The final board restores the GNSS feed's rear ground reference while preserving the engineer's RF routing and converter placement. The previously isolated converter and pressure-sensor ground groups now connect to the board ground network. The scoped geometric checks below pass. **The 0.75 mm RF line is retained for pilot qualification; it is not a qualified 50 Ω line.**

Reviewed PCB SHA256: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`. Incoming engineer PCB: `9428ded14dd46a084b5576b85987093bf20139053cdad33eb35cf222d1db2703`. Native extraction includes all saved filled polygons, pads, tracks/arcs, vias and copper graphics, reconciled against KiCad's whole-layer contours within 5 µm. No signal analysis substitutes for native DRC, schematic parity or the independent full-board connectivity review.

The reviewer identified the initial RF/power issues and authored the bounded C5 translation function. Root integrated it with the other local repairs; independent connectivity and mechanical checks remain separate evidence. The final analysis scripts here are read-only.

## GNSS reference and RF routing

| Check | Final result |
|---|---|
| U3.11 rear reference | Entire 1.44 mm² input pad backed by GND |
| Feed beyond AE2 pad plus 0.15 mm transition | Zero missing rear reference at 5 µm contour tolerance |
| Foreign rear copper under that feed | None |
| U3 ground pads and corridor grounds | Connected through actual copper and plated features |
| GNSS edge distance to boost / buck switch copper | 5.023 / 2.625 mm in projection |
| LoRa rear reference beyond its antenna transition | Continuous within the reported screen; no foreign rear overlap |

C5 moves down 1.30 mm to `(64.875,66.007)`, keeping its flat rear orientation, polarity and three 2.5 × 3.5 mm lands. Existing terminal routes still terminate within those lands; no signal rerouting was needed. Two nearby ground stitches move by 0.32 and 0.09 mm to preserve clearance. The mechanical review controls actual case/connector clearances and assembly limitations.

The main GNSS feed is approximately 13.534 mm, plus a 4.509 mm D3 shunt branch. Removing the redundant 2.254 mm coincident segment changes neither the copper union nor the RF path. The connected D3 branch remains. The saved front ground is finite and asymmetric near transitions; connectivity alone does not establish an uninterrupted guard of constant width.

The retained 0.75 mm feed has approximately 0.1505 mm side gaps along its long straight. The existing ideal grounded-coplanar calculation gives approximately 36.8 Ω at 0.15 mm gaps, or 40.8 Ω at 0.30 mm gaps, for the CAD's nominal 0.31 mm core, εr 4.5 and 35 µm copper. These are conditional values from an ideal uniform structure. Actual pad/diode transitions, finite grounds, mask and supplier tolerances are not represented. **Do not describe this board as impedance-qualified or infer measured GNSS performance from these numbers.** See the [model and limitations](../../v1_1_peer_review_20261014/rf/impedance.md).

[RF reference evidence](rf-reference.json), [projection measurements](rf-power-review.json), [launch diagram](rf-launch.png), [upper-board diagram](upper.png).

## Ground and power continuity

The following ground groups share the full-board return network: U1/C2/C3/C4/C6/C20, U3/C10, U8/C22/R25, U2/C7/C8 and U4/C11. The repair stitches at `(64.25,32.20)` and `(68.75,59.95)`, and the relocated C5-adjacent stitches at `(63.5,49.85)` and `(59.6,48.895)`, have actual annular copper contact on both faces. The checker joins layers only at native plated pads or vias, not at coincident projections. [Ground evidence](ground-review.json)

A bounded return-path limitation remains: converter grounds do not all connect within X62–77 / Y29–43.5 mm, but do connect when the lower boundary extends to Y46 mm. This identifies a return path outside the immediate converter neighborhood. It is not an open or a field/current-distribution model. Keep startup, ripple and radio-load transient measurements in the pilot acceptance work; do not equate full-board DC connectivity with a minimum-inductance loop.

All reviewed converter, bypass and balancer component poses and values remain as the engineer placed them. The complete LBOOST, LBUCK, GNSS-supply, SC_HALF_REF and SC_BAL_OUT copper unions are unchanged by the local repair pass on both faces, including their filled polygons. [Power continuity comparison](power-continuity.json)

The final local solar-loop cleanup retains the original 0.775 mm-wide, 2.100 mm C2-to-L1 supply route. The shortened U1 input branch ends at `(71.3,34.8)`, inside L1's positive land, and the native rear-copper union still directly connects C2.1, L1.2 and U1.VIN2. Removing the two redundant return segments changes no component pose or supply-net membership. This is a connectivity/geometry check, not an equivalent-resistance or switching-loop simulation.

The engineer's LBOOST and LBUCK connections use local filled polygons; a track-only calculation would miss them. Neither crosses RF. Some front 3.3 V copper and C21 lie opposite switch copper, which remains a rail-noise qualification item. The half-stack reference, balancer output and front VBAT routes have no projected switch overlap. C10's supply pad is 2.867 mm from U3.VCC8; C22's supply pad is 1.346 mm from U8.VBAT5. These are pad-center distances, not loop inductance.

The removed dangling 3.3 V via at `(69.59,33.13)` had no rear connection. Its front supply branch remains because it feeds the front supply polygon from C6 through the upper via at `(69.16,30.547)`. C8/C21 and all reviewed capacitor values remain. Prior effective-capacitance, cold-start, supercapacitor balancing and FB1 resistance limitations still apply. [Earlier component review](../../v1_1_peer_review_20261014/power/README.md)

Use the existing [complete-payload reception test](../../v1_1_top_gnss_20261014/reception-test.md), with this revision identified in the results, to compare fresh satellite C/N0, fix/acquisition behavior and supply waveforms with the solar harvester and LoRa quiet/active. Matching, radio coexistence, cold operation and real antenna/solar/string geometry remain bench and pilot qualification work.

## Reproduction

From the repository root, use KiCad's bundled Python for `extract_rf_reference.py` and `snapshot.py`, and the analysis virtual environment for the other scripts. Replace `PCB`, `DATA`, and `INCOMING_DATA` with explicit paths. The PCB may be the release checkout; the retained incoming board is `analysis/v1_1_engineer_review_20261015/intake/stratolink.kicad_pcb`. Scripts do not refill or save the CAD.

```
analysis/v1_1_peer_review_20261014/digital/extract_rf_reference.py --pcb PCB --output DATA/native-copper.json
analysis/v1_1_top_gnss_20261014/power/snapshot.py PCB DATA/native-layout.json
analysis/v1_1_peer_review_20261014/digital/check_rf_reference.py --geometry DATA/native-copper.json --output DATA/rf-reference.json
analysis/v1_1_engineer_review_20261015/rf-power/analyze.py DATA
analysis/v1_1_engineer_review_20261015/rf-power/check_ground.py DATA
analysis/v1_1_engineer_review_20261015/rf-power/compare_power.py --before-layout INCOMING_DATA/native-layout.json --before-copper INCOMING_DATA/native-copper.json --final-dir DATA
```

Create the incoming comparison snapshots with the same first two commands against the retained incoming PCB. `source-identities.json` pins the source and checker dependencies; output JSON embeds the PCB hash. No copied project assets are needed in this review directory.
