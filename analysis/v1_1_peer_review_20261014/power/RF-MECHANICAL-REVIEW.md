# RF-placement mechanical and power review

Final reviewed PCB: `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`. The layout passes the geometric and electrical checks below. Physical retention, solder access with actual parts, and RF performance remain pilot tests.

The manufacturer/source and mechanical comparison were independent of the RF author. This reviewer subsequently authored the bounded C5 routing patch and final copper cleanup; those changes require the separate digital reviewer's net, scope, and reference-plane checks. No canonical CAD or Git was changed by this reviewer.

## C5 placement and assembly

C5 moves 1.8 mm right to `(66.675,64.707)`, retaining its rear-side 180° orientation, flat model, all three lands, and terminal polarity. The CAP-XX Rev 1.9 drawing specifies a 30±0.5 ×14±0.5 mm case, 4.0 mm maximum thickness, 34.5 mm maximum overall length, and 4.5 mm maximum terminal protrusion. The conservative centered maximum case is `[59.425,49.457]` to `[73.925,79.957]`.

| Maximum-case projection | Final clearance |
|---|---:|
| Actual right-notch board edge | 0.747929 mm |
| J1 exposed ground bank | 0.4505 mm |
| J4 rear lands | 0.886 mm |
| Lower AE1 reserved solder/wire envelope, Y | 1.496 mm |

There is no projected case overlap with those features. The 2.5×3.5 mm lands and their existing nominal 3.5 mm pitch are unchanged; the midpoint land retains its existing 0.01 mm offset. The case-to-land gap remains 1.5 mm using the maximum case length. The pad row extends past the terminal tips for hand soldering; actual placement and solder fillets must be checked on the pilot. Case insulation, adhesive thickness, swelling, and extra hand-placement error are not included in the table.

A 2.3 mm right shift was rejected because its maximum case projected over the J1 ground bank. A 1.4–1.8 mm downward shift was rejected because it leaves only 0.096 mm or overlaps the lower antenna's reserved assembly envelope. The chosen sideways move preserves that lower access.

The original 16×37.25 mm rectangular courtyard used local bounds `x±8`, `y[-21.25,16]`. Its replacement uses `x±7.375`, `y[-20.375,15.375]`, or 14.75×35.75 mm. It encloses the manufacturer's maximum 14.5×30.5 mm case plus a 0.125 mm manual-assembly allowance; the upper boundary additionally follows the actual pad top at -20.25 mm plus that allowance, covering the terminals. Only the four existing courtyard line endpoints changed. This is a deliberately compact assembly envelope, not a tolerance qualification or extra physical clearance. The separate 0.4505 mm case-to-bank gap remains the relevant physical result.

CAP-XX prohibits soldering the case and normal capacitor reflow. Install the discharged capacitor after PCB reflow and cleaning, confirm the three terminals, and retain the flat case independently of solar-panel and antenna loads. The manufacturer's adhesive mounting used in its shock/vibration tests does not qualify an arbitrary balloon adhesive at altitude. The local library's stale Description and Assembly_Note now match the already-correct placed footprint; no schematic or placed-field changes were needed.

## GNSS antenna and nearby assembly

AE2 moves to `(55.3,47.85)`, 180°, with its existing 1.0 mm drill and 1.5 mm land. Native outline geometry gives 1.48336 mm of laminate between the hole and board edge and 1.23336 mm from copper land to edge. The 0.25 mm annular ring is unchanged. A chosen 1.25 mm-radius solder envelope leaves at least 1.17695 mm to FB1 copper and 1.44600 mm to C10 copper. These are layout allowances, not measured solder blobs or a pull/bend strength result for 0.4 mm FR4.

A native VRML export confirms the 48 mm wire points left. The retained local Y offset puts the nominal centerline from `(55.3,47.65)` to `(7.3,47.65)`. Its 0.321 mm modeled diameter is unmeasured. Raising only the nominal model Z offset from 0.15 to 0.25 mm removes the inherited 0.0105 mm display penetration and leaves 0.0895 mm above the board surface. Both the placed model and project-local GNSS footprint carry this correction; model path, length, scale, and rotation are unchanged.

The full nominal solar meshes remain at least 5.4895 mm away in Y. An upward, taut two-hole bridle remains at least 15.7445 mm away in Y. These static lower bounds do not cover panel flutter, loose string, knots, or bent wire. Antenna loading and orientation still require testing with the complete assembly.

## Power and balance verification

The hash-bound native check passes: U1/L1/L2/C2/C3/C4/C6 and U8/R24/R25/R26/C22 placements are exact; every LBOOST/LBUCK track is exact; C5's lands translate rigidly with unchanged sizes and nets. C5.1 remains `/VBAT`, C5.2 remains GND, and C5.3 remains `/SC_MID`; the active-balancer feedback topology is unchanged.

The C5 move required local routing changes to `/VBAT`, `/SC_MID`, the 0.38 mm +3.3 V trunk, 0.25 mm SCL, and ground returns. SC_MID now uses two vias and a front-side descent inside the stationary GNSS module, avoiding the RF reference corridor. Four ground stitches move around the new rail corridor; one redundant stitch in the newly isolated under-module ground pocket is removed. These are explicit changes to non-switching interconnects, not a claim that all power copper stayed identical. Native DRC, opens, and schematic parity are zero. The separate review verifies all physical pad islands and the final RF ground reference.

Evidence: [final native power checks](rf-final-power.json), [final mechanical results](rf-assembly-review.json), [native mechanical inputs](rf-assembly-native.json), [alternative poses](c5-pose-screen.json), [C5 routing script](../rf/route_c5.py), [cached manufacturer drawing](../../v1_1_layout_20261012/flat_storage/sourcecaptures/dmf1f_mechanical.png), [CAP-XX primary PDF](https://cap-xx-assets.s3.eu-west-2.amazonaws.com/CAP_XX_DMF_1_F_Datasheet_V1_9_c35f3f99e6.pdf).
