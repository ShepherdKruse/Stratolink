# Copper cleanup candidate, 2026-10-14

The final isolated candidate is `copper-final4/stratolink.kicad_pcb`, SHA-256 `4fcdb39b8cc7936295f64ae9f5e1acd4acd01e144cd21e9076f681c23c0e2b54`. Root owns promotion. This work did not change canonical CAD, the BOM or the supplier cart.

The source is published commit `e6f5200208cf433aa2baf0dcad80d9d9ef26cd25`, PCB hash `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`. The user's unrelated current project edits were not used or overwritten. The strict candidate project adds durable 0.10 mm groove/connection constraints and sets both associated DRC checks to error.

Changes are local copper repairs:

- Add a 0.35 mm explicit U8.4-to-balancer-via landing, retaining the via location and drill. This removes the near-tangent 0.0196 mm contact region.
- Close the front ground crescent beside the PA8 via, the four tiny front U1 ground voids, and the tiny rear buck-output void. The switching nodes are unchanged.
- Widen the U6.1-to-U6.2 ground bridge from 0.15 to 0.20 mm and round its remaining fine seam.
- Add 30 net-assigned local fillet polygons at the independently identified electrical notches and remaining hairlines. The nominal fillet radius is 0.075 mm. Add one short rear ground stitch where two polygon approximations created a near-collinear seam.
- Remove exactly three tiny logo islands and fill only the 0.004664499 mm² internal logo hole. The main logo polygon is unchanged. The removed islands total 0.011042493 mm².
- Preserve the visible copper labels as 31 exact native rendered outline polygons with 12 local rounding patches. Retain the two original editable text objects on F.Fab and group each with its copper shapes. This avoids silkscreen and keeps each label movable as a unit. Native KiCad rejects overlapping copper patches on an editable PCB_TEXT object as shorts, which is why these two labels required conversion.

All original component placements, pads, vias, board outlines and track centerlines remain unchanged. One existing track width changes, and six short tracks are added. Small same-net fillets alter copper at the inherited antenna notches; this is not an RF performance correction. The separate GNSS placement/RF review still controls the release hold.

[Before/after PDF](before-after.pdf) and [PNG](before-after.png) show the physical copper changes. [Manifest](manifest.json) and the three change ledgers list every affected/added UUID, coordinate and net: [initial repairs](copper-fix-changes.json), [fillets and logo](fillet-changes.json), [label groups and rear stitch](text-and-seam-changes.json).

Validation: native KiCad 10 DRC, schematic parity and connectivity all report zero issues with strict rules and refilled zones. The whole-board screen reports zero acute gaps under 60° with at least 0.075 mm edge support, zero tips under 30°, zero enclosed gaps below both 0.02 mm² area and 0.10 mm inscribed diameter, and zero copper islands under 0.01 mm². These are explicit geometric screening thresholds, not a guarantee about every possible etchant process or factory CAM approval. Existing component clearances and all electrical connectivity still require the ordinary supplier and physical review.

The `final3` prototype was rejected before promotion: a raw polygon-hole selector chose the surrounding ground-clearance cavity instead of the small nested logo hole. The corrected build starts again from the untouched intermediate and asserts the intended hole's area and bounds. Exact full-union logo additions/removals were checked, and the corrected before/after image was visually inspected. Passing DRC alone did not catch that artwork error.

Run `python3 analysis/v1_1_peer_review_20261014/fabrication/reproduce_cleanup.py /absolute/new/path/under/ai-working/scratch/` to rebuild from the published Git object. The script does not mutate Git or canonical CAD. It reproduced the final PCB hash exactly and again passed strict native checks. The frozen fillet plan and logo polygon are retained here; native geometry and screening scripts live one directory above.
