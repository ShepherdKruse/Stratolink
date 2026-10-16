# Filled-copper manufacturing review

Final PCB: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`.

Native strict DRC, connectivity and schematic parity report zero violations after the two local copper corrections. The filled-copper screen also found two enclosed electrical etch pockets that native DRC did not report. Both were corrected:

- The UV ground zone had a 0.00387 mm² enclosed void with a 0.0463 mm maximum inscribed diameter. Filling one 0.39 by 0.53 mm notch in the existing zone outline removes the void. A smaller chamfer was tested and rejected because it left two smaller voids.
- A redundant +SOLAR loop beside L1.2 enclosed a 0.01624 mm² triangular gap. The diagonal track now ends in L1.2 along its original centerline. Its redundant 0.275 mm and 0.84853 mm branch segments were removed. The shortened tail removes a further 0.84146 mm of centerline, for 1.96499 mm total. No footprint or unrelated route changed.

`repair_local_copper.py` applies those exact edits to the pre-correction PCB hash `2d053c2...`. `local-copper-scope.json` verifies all other source nodes are identical, apart from regenerated fills. `local-copper-ledger.json` records the dimensions and verifies that a single combined application reproduces the final hash. `local-copper-drc.json` is the native result from that reproduction.

Twelve electrical reentrant wedge terminations remain. They are shown in `electrical-wedge-closeups.png`, with exact coordinates and source items in `classified-screen.json`. Their angles are 45.0 to 47.2 degrees. Each measured opening exceeds 0.10 mm width by 0.125 mm from its apex. Eleven open into a clearance region connected to the board edge. The GNSS wedge opens into its 6.126 mm² clearance moat. None is a separate tiny enclosed pocket after the repairs. These measurements support retaining the engineer's routing for supplier review; they do not establish that every sharp gap will reproduce exactly or that the design is categorically free of acid traps. JLC CAM review remains outstanding.

The unnetted copper lettering contributes 12 further acute-angle screen candidates. The decorative logo contains five tiny copper components, 0.00052 to 0.00964 mm², and two small enclosed gaps with maximum inscribed diameters about 0.040 and 0.064 mm. They are not orphan electrical ground fragments, but some detail may not reproduce. Their dimensions and positions are retained in `final-screen.json`; supplier CAM should review the artwork alongside the electrical wedges. No decorative artwork was changed.

The screen requests native full-copper polygons at 2 µm approximation, simplifies by 2 µm to suppress tessellation artifacts, and requires 0.075 mm adjacent-edge support before reporting a corner. It flags gaps below 60 degrees, tips below 30 degrees, enclosed gaps below 0.02 mm² and 0.10 mm inscribed diameter, and copper pieces below 0.01 mm². The thresholds identify review candidates; they are not supplier process guarantees. No sharp copper-tip candidates were found.

Reproduction:

```sh
KICAD_PYTHON extract_geometry.py --pcb CANDIDATE/stratolink.kicad_pcb --output final-geometry.json
ANALYSIS_PYTHON screen_geometry.py --geometry final-geometry.json --output final-screen.json
ANALYSIS_PYTHON classify_screen.py --copper ../connectivity/final-copper.json --screen final-screen.json --output classified-screen.json
ANALYSIS_PYTHON review_wedges.py --geometry final-geometry.json --classified classified-screen.json --output wedge-review.json --figure electrical-wedge-closeups.png
```

`electrical-wedges.csv` is the compact numerical table. `wedge-review.json` retains the full width profiles and empty-region areas. Native geometry checks and CAM review do not replace physical assembly, optical or RF validation.
