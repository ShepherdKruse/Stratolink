# Independent suspension fabrication review

**Pass** for candidate PCB SHA-256 `82926d9dfc728dca41c9d0970c69a5144fb9079380a298337381c199698f80f4`. The review opened the candidate read-only and inspected its native pads, ground connectivity, board-profile polygon and actual exported Gerber/Excellon commands. It did not rely only on the builder's dimensions.

- H1 is at (55.665, 31.745) mm and H2 at (74.327, 31.745) mm. Each has a **2.0 mm plated round drill**, **3.2 mm copper OD** on both faces and **0.6 mm nominal annulus**.
- Actual front/back copper and mask Gerbers each contain both 3.2 mm circular flashes at those positions. No H1/H2 aperture appears in either paste export.
- Both top holes occur once in the **PTH** Excellon with the 2.0 mm tool and never in the NPTH file. Total PTH hits are **167**. The NPTH file correctly retains three unrelated, existing 0.991 mm holes near the lower board; it is not expected to be empty.
- The native board profile is one valid outline with **zero internal routed cutouts**. Both drill centers are inside its laminate profile, confirming the previous top Edge.Cuts circles were removed. The new holes are manufactured from the plated drill layer.
- Each H1/H2 reaches all **67 original logical GND nodes**, with 69 nodes including H1/H2. Native unconnected count is zero.
- Source PCB hash is unchanged by this review. The independently checked export hashes are recorded in [independent-review.json](independent-review.json).

This verifies plating instructions, dimensions and electrical connection. It does not measure string abrasion, laminate fatigue, plated-wall finish, proof strength or RF performance. The mechanical qualification and inherited whole-board fabrication findings remain separate.
