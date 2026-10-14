# Mechanical review of the restored top GNSS antenna

The final board restores the flown **AE2 top feed at (62.882,33.218) mm, 90°**, with its **48 mm straight wire upward**. It keeps the antenna farther from the modeled conductive solar assembly than the rejected side exit and restores the larger board-edge ligament. This supports the placement mechanically; it does not establish an optimal radiation pattern or guarantee clearance from the moving suspension string.

This report binds to PCB SHA256 `88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`. Final D3 is at `(58.8,42.0)`, 0°. L1 moves 0.5 mm right on the rear; U3 and U8 stay fixed. The C5 rear fit and +1.8 mm X shift remain. No remote side-pad-to-upward-wire workaround is used.

| Nominal static geometry | Final top/upward | Rejected left exit |
|---|---:|---:|
| Smallest wire-to-solar-assembly gap | ≥21.58 mm | ≥5.50 mm |
| Wire to conductive terminal metal | ≥22.20 mm | ≥6.19 mm |
| Wire to modeled cell fingers | ≥24.51 mm | ≥6.20 mm |
| Wire to positive copper lead | ≥52.03 mm | ≥35.11 mm |
| Antenna-hole edge to board outline | 3.321 mm | 1.483 mm |
| Antenna copper-land edge to board outline | 3.071 mm | 1.233 mm |

These compare the final original-top pose with the prior side exit `(55.3,47.85)`, 180°. The closest solar object is the left ground solder fillet. Distances are analytic segment-to-triangle distances against every nominal solar mesh, minus the 0.1605 mm wire radius. The conservative capsule envelope slightly exceeds a cylinder's flat end cap. The existing photo-derived solar geometry, assumed film thickness, curvature, solder fillets and flexible leads are not measured production tolerances. Greater separation is useful geometric evidence, not a substitute for full-assembly antenna impedance, pattern or GNSS reception measurements.

The retained model places the nominal wire centerline from **(63.082,33.218,0.45) to (63.082,−14.782,0.45) mm**. Native model orientation was checked against KiCad's upward transform. Its 0.2 mm X offset lies inside the 1 mm drilled hole. The modeled lower wire surface is 0.0895 mm above the board front. The 0.321 mm diameter and model elevation remain unmeasured display assumptions, rather than an exact solder-bend instruction. The centerline's projected gap to H1's plated annulus is 5.657 mm; the antenna land-to-H1-annulus gap is 5.016 mm.

H1/H2 remain `(55.665,31.745)` and `(74.327,31.745)`. For a symmetric suspension triangle, the apex is at X64.996. Its left leg crosses the antenna's **XY projection** when the apex is up to about **58.53 mm above the hole centers**. Heights 20–50 mm project crossings; at 60 mm the centerlines miss by only 0.179 mm, and at 80 mm by 1.977 mm. These are conditional scenarios, not measurements of Teddy's string. A projected crossing can be clear if the string stays behind the board. At a crossing, depth separation must exceed the 0.1605 mm wire radius plus half the actual string diameter and an allowance for motion. Check the actual loop, knot and flexible wire together before launch. [Projection and scenarios](assembly-projection.png)

C5's unchanged maximum case envelope is **30.5×14.5 mm**, using the CAP-XX DMF drawing's ±0.5 mm length/width tolerance; maximum thickness is 4.0 mm. At its retained rear pose `(66.675,64.707)`, the maximum case rectangle is X59.425–73.925/Y49.457–79.957. It clears the board outline by 0.748 mm, the exposed J1 ground bank by 0.451 mm and J4 rear lands by 0.886 mm. These are static projected case clearances. Real placement tolerance, terminal solder, case insulation, standoff/adhesive and solar flex still need assembly review. [Manufacturer drawing, Table 3/page 2](https://cap-xx-assets.s3.eu-west-2.amazonaws.com/CAP_XX_DMF_1_F_Datasheet_V1_9_c35f3f99e6.pdf)

Evidence: [hash-bound assembly review](assembly-review.json), [native geometry](final-native.json), [model/source identities](source-identities.json). The solar geometry comes from `hardware/pcb/3d/solar/generate.py`; no new dimensions were invented for this change. Reproduce the native input with `analysis/v1_1_peer_review_20261014/power/snapshot_assembly.py PCB OUTPUT.json` under KiCad Python, then run `review_top_assembly.py --native OUTPUT.json --solar-dir hardware/pcb/3d/solar --output REPORT_DIRECTORY` under `analysis/.venv/bin/python`. `geometry_distances.py` provides the analytic segment/triangle distance calculation. All scripts leave CAD unchanged.
