# Final top-GNSS copper cleanup

This bounded patch transforms the RF author's immutable `7e401900a78b7d88c4e688fdbe58039308113fc0308e5125366d0a98c592a502` candidate into final PCB **`88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`**. Functional routes, tracks, vias, footprint poses, pad geometry/nets, artwork and board outline remain unchanged. The patch adds three same-net rounded copper junctions and changes only the explicitly listed ground-zone outlines. [Exact UUID/geometry ledger](cleanup-ledger.json)

| Repair | Scope |
|---|---|
| Front H1 ground junction at (57.0,32.621221) | Local GND fillet |
| Rear L1 LBOOST junction at (61.775987,40.3915) | Local same-net fillet |
| Rear L1 +SOLAR junction at (62.380053,37.4415) | Local same-net fillet |
| Seven disconnected ground fill fragments near the receiver/artwork | Five local holes in their source zone outlines; one hole combines three nearby fragments |
| New rear solid RF-zone boundary | Upper east edge X63.5; below Y34.2, X62.6; preserves C1/C2/R2's inherited 0.5 mm thermal neighborhoods |

The fourth original acute junction, at (64.6,39.354079), disappears when that rear zone boundary moves. No filler remains at its obsolete position. R25.GND remains intentionally solid where needed for the rear RF reference. No per-pad thermal metadata or global clearance/fill policy changes are introduced.

The rounded fills use a 0.075 mm local closing radius with a 0.015 mm overlap into existing same-net copper. Fleck exclusions affect only the source zones, whose connected main copper is at least 0.5 mm away from the small exclusions and over 1.5 mm away from the combined cluster. This prevents native refill from regenerating nearby fragments without cutting the functional guard zones. It is a saved, reproducible outline change, not a manual edit of generated fill polygons.

Strict native DRC reports **zero violations, zero opens and zero schematic-parity issues**. The independent all-net/reference review is recorded separately. The full-copper screen finds **zero substantive acute gaps or sharp tips**. Seven real disconnected fill fragments are gone. Five tiny remaining rear components and five enclosed seams have maximum inscribed widths below 10 nm; they are polygon-intersection/tessellation artifacts, far below the 100 µm fabrication feature screen. They remain visible in the raw report rather than being misrepresented as zero raw candidates. [Full screen](final-screen.json), [classified union comparison](cleanup-review.json)

Front copper changes by +0.004902/−0.000083 mm². Rear copper changes by +0.019053/−8.079468 mm², primarily from restoring the power pads' thermal neighborhoods and removing the unnecessary east extension of the solid RF zone. All meaningful differences lie in the declared repair regions. Outside these regions, the residual changed area is 0.000000652 mm² of submicron tessellation differences. This explicit union comparison prevents a broad accidental artwork or zone fill from passing merely because DRC is clear.

The portable entry point was run successfully and reproduced the exact final PCB hash with zero native violations/opens/parity issues. It accepts explicit paths, refuses to overwrite an existing output or the canonical/source project, and permits alternative KiCad executable locations:

```sh
python3 analysis/v1_1_top_gnss_20261014/fabrication/reproduce_cleanup.py \
  --source-project /path/to/reconstructed-7e401-project \
  --output-project /path/to/new-isolated-project
```

[Checked reproduction result](reproduction.json). The absolute paths retained in that evidence record describe the executed run, not mandatory input locations.

Reproduction uses the RF author's hash-bound candidate from `../rf/` and does not require an unpublished scratch script:

1. Reconstruct or copy the author candidate into an isolated project under `~/Repositories/ai-working/`, verifying source SHA `7e401…`. Retain its project, schematic, rules and local libraries.
2. With `analysis/.venv/bin/python`, run `plan_cleanup.py --items source-items.json --screen source-screen.json --flecks source-flecks.json --output PLAN.json`. The committed `cleanup-plan.json` is the frozen equivalent.
3. With KiCad's bundled Python, run `apply_cleanup.py --pcb CANDIDATE.kicad_pcb --plan cleanup-plan.json --ledger LEDGER.json`.
4. Run `kicad-cli pcb drc --refill-zones --save-board --schematic-parity --severity-all --format json --output DRC.json CANDIDATE.kicad_pcb`.
5. Use `extract_and_screen.py extract --repo REPO --pcb CANDIDATE.kicad_pcb --output DIRECTORY` under KiCad Python, then `extract_and_screen.py screen --repo REPO --output DIRECTORY` under the analysis environment. `verify_cleanup.py --before source-geometry.json --after DIRECTORY/final-geometry.json --plan cleanup-plan.json --output REPORT.json` checks the bounded union changes and classifies the numerical remnants.

The wrapper imports the repository's existing native extractor and geometry screen from `analysis/v1_1_peer_review_20261014/fabrication/`. Source input hashes, frozen geometry and deterministic UUIDs are retained here. None of these scripts edits canonical CAD.
