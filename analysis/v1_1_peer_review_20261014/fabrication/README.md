# Fabrication geometry review, 2026-10-14

The released board has two narrow copper connections and several very small enclosed copper gaps that its original DRC settings did not flag. The corrected `copper-final4` scratch candidate passes independent strict native DRC, source-scope checks, and all four whole-copper geometry screens on both faces. Its logo repair was checked by exact copper-area differences after an earlier candidate selected the wrong empty region. This is a pass under the stated geometric thresholds, not a guarantee about every possible fabrication process. Subsequent RF edits require a fresh check.

This review is read-only against canonical CAD. Scratch changes are owned by the CAD agent. No manufacturing package or cart was changed by these scripts.

## Inputs and method

- Released PCB SHA256 `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`.
- Flown comparison PCB from commit `9bdd19ec707455271f48f5a5d8be352fc696cf9c`, SHA256 `2924cfa59d48c1446488d715834e84ea634516e622ed59915fb72521e9595190`.
- Native saved copper unions include tracks, pads, filled zones, copper lettering, and graphics. The analysis does not infer copper from screenshots.
- The original project has `min_groove_width=0` and `min_connection=0`. The diagnostic scratch project uses the published project's strict mask rules and sets both minimum groove and minimum connection widths to 0.10 mm. Current local user edits to canonical project settings are preserved.
- The geometric screen simplifies boundary tessellation by 2 µm, requires adjacent edges of at least 0.075 mm, and flags reentrant gap angles below 60°. This is a candidate finder, not a manufacturer etching simulation.
- Small enclosed empty regions are reported if their area is below 0.02 mm² and maximum inscribed diameter below 0.10 mm. Tiny copper components below 0.01 mm² are listed separately. These diagnostic thresholds are not blanket fabrication limits.
- Copper polygons here do not subtract the physical drill bores. The four U1 triangular voids therefore cannot be explained as drill holes.
- Submicron seams are below meaningful curve-polygon accuracy and fabrication resolution. Their presence identifies near-coincident source boundaries; their reported dimensions must not be interpreted as accurate etched dimensions.

JLC's [layout DFM guidance](https://jlcpcb.com/features/layout) identifies acute trace angles as potential acid traps. It does not provide a probability of failure or certify this board. The source text was captured through the in-app browser in `../sources/jlc-layout-dfm.txt`. Passing KiCad's copper-sliver test does not prove the absence of all enclosed voids or acute junctions.

## Definite findings in the released board

The stricter native DRC produces two `connection_width` warnings, no `copper_sliver` warnings, and no opens or schematic parity problems:

| Feature | Layer and position | Native reported width | Required disposition |
|---|---|---:|---|
| U8.4 `/SC_BAL_OUT` to nearby via | B.Cu, pad `(56.7875,35.15)`, via `(57.5,35.65)` | 0.0196 mm | Add a broad explicit landing; do not rely on near-tangent copper contact |
| GND route/zone connection | F.Cu, around `(70.25,62.07)` | 0.0624 mm | Join the same-net local copper across the narrow crescent |

Both GND track segments in the second finding are 0.25 mm wide and share an endpoint. The warning is about the local union/zone connection, not proof that the two track centerlines fail to meet. Likewise U8.4 has another route leaving the pad, so the narrow pad/via contact alone is not proof that every current path is this narrow.

The additional whole-copper screen finds these true small enclosed voids:

| Feature | Position(s), mm | Maximum inscribed diameter | Disposition |
|---|---|---:|---|
| Four front U1 GND triangles | x≈67.02/67.36, y≈37.60/38.03 | 0.053 mm each | Fill same-net triangles while preserving U1 thermal-pad/paste/drill geometry |
| Rear L2.2 output-rail triangle | `(71.2134,41.7127)` | 0.0318 mm | Fill locally on `+3.3V`; this is not a GND or switch-node void |
| Long front GND crescent | `(70.3948,62.325)` | 0.0475 mm | Fill with neck correction |
| Short front GND seam | `(70.2036,62.8648)` | 0.0094 mm | Remove near-coincident same-net gap |
| Rear inherited GND seam | `(75.0644,80.9407)` | ≈0.0005 mm | Remove source near-coincidence; numeric width is below modeling accuracy |
| Front logo hole | `(62.6677,56.9584)` | 0.0545 mm | Fill this sub-resolution decorative hole |

A front U6.2 GND junction has a reentrant hairline at `(73.8245,35.6)`. Widening its connecting track shifts the notch rather than necessarily eliminating it. Exact overlap or an explicit local fill is needed if the intent is to remove the source seam.

Three isolated front logo specks have bounds of about 0.131×0.085 mm, 0.039×0.052 mm, and 0.038×0.038 mm. These are real copper artwork primitives. Their inherited status does not make them manufacturable details. Removing the three specks and filling the tiny logo hole is the smallest artwork correction; it preserves the recognizable logo.

## Open corners and artwork

The released board has 36 front and 11 rear acute-gap candidates under the stated screening thresholds. Twelve front candidates are ordinary glyph corners belonging to the copper texts `PICO MAINBOARD V1.1` and `STRATOLINK.ORG`; exact native text polygons verify that attribution. The remaining 35 candidates are electrical copper boundaries, including the eight corners of the four U1 triangles and both inherited antenna-route bends.

Open 45° same-net junctions are different from tiny enclosed pockets, but they still narrow toward an acute vertex. They have not been certified harmless merely because they are inherited or because native DRC is clean. The text glyphs have 25° to 50° corners; inheritance is not a pass for those either. A whole-board no-acute-corner goal requires a declared disposition for these remaining points, such as local rounded copper blends or artwork cleanup, followed by a new native and exported-artwork check. No blanket zero-acid-trap claim is made here.

`all-candidate-classification.json` records every baseline candidate, nearest electrical UUIDs/nets, and exact artwork identity where applicable. `geometry-details.png` shows representative native copper unions.

## First cleanup candidate check

Candidate `copper-fix/stratolink.kicad_pcb`, SHA256 `4fc14170fc8452f4b4fd7ec097bfb0bcdde89e63024ddc5af3e52abfd173d9ea`, is an intermediate scratch result, not canonical CAD.

Independent union extraction confirms the four U1 triangles, L2.2 rear triangle, and long GND crescent are gone. The short front GND seam, rear submicron seam, front logo hole, three logo specks, and a shifted U6 GND notch remain. Counts become 28 front and 11 rear acute candidates, two front small closed gaps, one rear small closed gap, and the three inherited tiny front artwork components. The CAD agent reports a clean strict native DRC for this exact intermediate; that result and the remaining geometry candidates are compatible.

This intermediate is superseded by the checked final4 candidate below. Its remaining-feature counts are historical evidence, not the current result.

## Corrected final cleanup

Independent review of `copper-final4/stratolink.kicad_pcb`, SHA256 `4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54`, passes:

- Native DRC with 0.10 mm minimum groove and connection widths, strict mask rules, and error-level copper-sliver/connection-width checks: zero violations, opens, and schematic parity problems.
- Whole native copper union: zero acute-gap, sharp-tip, small-enclosed-gap, and tiny-component candidates on either face under the documented thresholds.
- All 68 footprint structures, all vias, stackup/setup, net definitions, and outline primitives are unchanged. All original tracks remain; one declared GND track widens from 0.15 to 0.20 mm, and six declared local tracks are added.
- Forty-three added polygon net assignments match the change ledgers. Original texts remain editable on F.Fab; their native rendered outlines plus local rounding remain as copper artwork. There is no silkscreen artwork.
- The logo window adds exactly 0.004664499 mm² at the intended tiny hole and removes exactly 0.011042493 mm² for the three tiny specks. The recognizable logo remains.

The rejected `copper-final3` passed DRC and the candidate screen but added an erroneous 18.25 mm² artwork polygon. A raw ground-polygon hole contained the logo and the target point, so choosing the first containing hole selected the wrong region. Independent whole-copper union differences caught this. Final4 selects the connected empty region from board outline minus the union of **all** copper, then asserts its area and bounds. This is why source-scope and visual review accompany a zero screen count.

The checked scratch result is evidence for subsequent work, not a claim that canonical CAD or the saved order package has already been updated. See `copper-final4-independent-review.json`, `copper-final4-scope.json`, and `copper-final4-independent-drc.json` for exact hashes and counts.

## Evidence and reproduction

- `groove-0p10-input.json`, `groove-0p10-drc.json`: isolated diagnostic project and native DRC.
- `extract_geometry.py`: read-only native saved geometry, with source-hash assertion.
- `screen_geometry.py`, `geometry-screen.json`: baseline and flown candidate screen.
- `extract_artwork.py`, `artwork-geometry.json`: exact native copper text/graphics.
- `classify_all.py`, `all-candidate-classification.json`: complete candidate provenance.
- `copper-fix-geometry.json`, `copper-fix-screen.json`: independent intermediate candidate check.

Native extraction uses KiCad's bundled Python at `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9`. Geometric analysis uses `analysis/.venv/bin/python` with Shapely 2.1.2 and matplotlib. Neither extraction nor screening refills or saves a source PCB.
