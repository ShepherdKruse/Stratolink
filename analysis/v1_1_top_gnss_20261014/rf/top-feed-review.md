# Top GNSS feed revision

Status: **final native routing and author cleanup-scope review accepted**, bound to PCB SHA256 `88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`. The final cleanup removes the seven substantive source-fill fragments and four acute gaps, and trims the rear RF zone to preserve C1/C2/R2 thermal policy. R25.GND is intentionally solid beneath the RF projection. This is a geometric and electrical-connectivity review; it does not establish RF performance or authorize ordering.

The candidate restores the flown GNSS antenna hole at **(62.882, 33.218) mm** and the **48 mm upward wire**. It keeps the receiver, solar attachments, outline, 0.4 mm stackup, and shifted flat rear capacitor placement. The feed now goes west of L1 with rear ground beneath it, instead of crossing the boost switching trace. The earlier leftward-wire revision and the intermediate top-left hole at (59.2, 32.4) are superseded layout trials.

## Native evidence

- Source PCB SHA256: `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`.
- Routing candidate SHA256: `7e401900a78b7d88c4e688fdbe58039308113fc0308e5125366d0a98c592a502`.
- Final reviewed PCB SHA256: `88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`.
- Strict project SHA256: `915d9f9c4bc8c1eb0866031bf765ff08dc41a7b5bea4fb158ca26c1032ef93cd`.
- KiCad native refill, DRC, and schematic parity: **0 violations, 0 unconnected items, 0 parity errors**.
- A fresh invocation of [build_top_feed.py](build_top_feed.py) from its final repository path, followed by KiCad 10.0.0 native refill, reproduces the exact candidate PCB hash. It refuses to overwrite an existing output folder or use an unexpected source/project. The input board is available in commit `d6dc7d3`.
- [Change ledger](routing-phase/changes.json), [native DRC](routing-phase/drc.json), [reference projection](routing-phase/reference.json), and [reproduction record with source-file hashes](routing-phase/reproduction.json) bind this routing phase. They intentionally retain the pre-cleanup hash.
- [Final native DRC](../fabrication/drc.json), [cleanup ledger](../fabrication/cleanup-ledger.json), [independent cleanup scope](cleanup-scope-review.json), [final rear reference](final-reference.json), and [actual thermal review](thermal-review.json) bind the final hash. The cleanup preserves every pad, track, arc, via, footprint, label, and zone connection setting from the accepted routing phase. Only three same-net copper fillets and three source-zone contours change, plus their regenerated saved fills.
- The [independent electrical review](../independent/README.md) binds final connected guards, full pad connectivity, artwork anchoring, and disposition of numerical contour seams. The [power review](../power/README.md) confirms the retained 0.25 mm rear C2-to-U1 ground path, including its three unchanged native tracks and 1.9864 mm centerline length.
- Full saved-copper extraction includes board and footprint copper shapes, including the rear unnetted graphic. The four remaining copper text objects are solar marks outside the RF corridor; native DRC includes them.

The frozen routing source is under `~/Repositories/ai-working/scratch/stratolink-top-gnss-20261014/rf-author/candidate-original-top/`; final cleanup is under the sibling `copper-cleanup/` folder. Full temporary project copies remain outside this repository. [Cleanup reproduction instructions](../fabrication/README.md) describe the second, separately hash-bound stage.

## Exact placement and routing scope

- **AE2:** returns to (62.882, 33.218), 90 degrees. The same 48 mm model and previously reviewed 0.25 mm display offset remain. The F.Fab assembly note now says upward from the top feed.
- **L1:** moves 0.5 mm right, from (60.103, 38.1865) to (60.603, 38.1865), on the rear. Its terminal connections move with the pads. No switching vias or width reductions are introduced. LBOOST does change locally, so it must not be described as unchanged.
- **D3:** moves to (58.8, 42.0), 0 degrees. Its RF pad meets the main feed directly; its ground pad has a nearby return stitch.
- **Branding:** the entire PICO group moves 0.6 mm left and the entire STRATOLINK group moves 0.4 mm left. Glyph geometry, lettering style, group membership, and editable F.Fab originals are retained.
- **GNSS feed:** 0.45 mm wide, with native rounded bends. It passes left of L1, then approaches the original antenna pad from the west.
- **+SOLAR:** the redundant left perimeter branch is removed. The retained right supply path now descends through (64.05, 31.921), (64.05, 34.7), and (63.4, 35.35), then joins C2. The existing local C2-to-U1 and C2-to-L1 paths are retained except for L1's shifted terminal endpoint.
- **/SC_BAL_OUT and the low-current /VBAT balancer/sense branch:** reroute around the top of the antenna endpoint, then descend to the right of the RF corridor. /SC_HALF_REF and C22 placement remain unchanged. This rerouting is required to avoid slicing the rear reference beneath the new feed.
- **GND:** obsolete crossing stitches/straps are removed, local RF reference fills are added, and a stitch near (58.7, 32.7) connects the upper ground region. C1/C2/R2 retain their existing pad connection settings; the final solid zone excludes each pad's full 0.5 mm thermal neighborhood. R25.GND intentionally has solid rear reference copper. The actual surrounding fill differs from the older layout, so restored thermal policy must not be described as identical copper geometry.

SCL, SDA, VSTOR, LoRa RF, C5's balance-terminal route, and all other footprints are outside the intentional signal/placement scope. Ground pours and some adjacent ground connectivity necessarily change. Independent checks preserved all 259 pad identities and 250 logical connections, the intended three footprint transforms, and the exact 45 translated artwork objects.

## What the geometry establishes

The new feed is **16.9634 mm**, compared with the original **13.4392 mm**, an increase of **3.5241 mm (26.2%)**. This is longer because it goes around the inductor rather than across its switching connection.

Outside the deliberately unreferenced plated-hole transition, the saved native geometry shows:

- no foreign rear copper overlapping the feed;
- complete rear ground beneath the trace and receiver RF pad, within a stated 5 micrometre contour-comparison tolerance;
- no direct LBOOST or LBUCK crossing;
- receiver-connected front ground on both sides at all 561 independent non-pad samples. Final minimum contiguous strip widths are 0.199 mm on the west side and 1.3246 mm opposite it; the largest first gap is 0.1754 mm. These finite, asymmetric strips do not establish uniform impedance.

The raw residual outside a nominal 0.9 mm pad exclusion is a roughly 0.5 micrometre contour approximation at the plated transition. It is reported rather than hidden by rounding.

The nearest projected edge of LBOOST remains approximately **0.167 mm** from the RF copper near L1. Moving past a switching node is not electromagnetic isolation: magnetic coupling from the inductor, fringe fields, return-current distribution, and receiver desensitization still require physical validation. Two-sided ground cannot be described as a shielded enclosure.

The final cleanup adds approximately 0.00648 mm² of LBOOST copper and 0.00622 mm² of +SOLAR copper at declared local fillets. The rear ground union loses approximately 8.07 mm², predominantly from the deliberate retreat of the solid RF zone around inherited thermal connections; it is not merely a microscopic cleanup. The ground changes remain within the explicit repair and thermal-zone regions. Outside those regions, the largest measured delta width is below 2 nanometres, consistent with polygon-intersection seams. These residuals are reported numerically rather than accepted as fabricated narrow features.

## Impedance and assembly limits

The existing [impedance screen](../../v1_1_peer_review_20261014/rf/impedance.md) uses the board-declared 0.31 mm core, 35 micrometre copper, and epsilon-r 4.5. A 0.45 mm trace with a 0.15 mm coplanar gap is approximately 48.5 ohms only under the model's idealized continuous, wide-ground assumptions. The actual finite guard widths, pad transitions, mask, nearby copper, inductor, and wire antenna require a more complete model or measurement. Do not call this a qualified uniform 50 ohm feed.

The upward model preserves the flown antenna's location and direction. The tip pointing upward does not establish best satellite coverage: a straight wire's pattern, polarization, board/panel loading, and payload attitude matter. The original bridle still needs physical separation from the wire, including slack, stretch, and motion. The 0.25 mm model offset is an assembly visualization assumption rather than a measured bend clearance.

Before flight, compare GNSS acquisition and C/N0 with the converter active and across the intended daytime supply range; check the assembled antenna match and orientation; and inspect the wire/string and soldered feed assembly. A passing PCB rule check does not replace those measurements.
