# Independent top-GNSS review

Accepted PCB: `88f82c85d2d47b4aea2e7d7d2827c4a92c339788cc0d9c880dd6342ee0440c0a`.
Compared with the preceding left-feed PCB `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`.

- All 259 physical pads and 250 logical connected-pad sets are preserved; native opens remain zero. Only AE2, D3 and L1 have declared rigid placement changes. C5, U3, all other parts, outline, stackup and pad metadata are unchanged. All 158 strict-review project/library/model files match the prior strict-review bundle. The canonical user project retains its separately bound local settings; the 157 other files match directly.
- The PICO and STRATOLINK copper groups move exactly 0.6 and 0.4 mm left; their 45 member shapes remain rigid. One assembly note changes LEFT to UP. Other unnetted artwork is unchanged. Every net-assigned graphic leads to an actual same-net pad through saved copper and real plated joins; touching orphan clusters cannot pass this check.
- Native RF trace length is **16.963388 mm**. The complete feed beyond AE2's land plus 0.15 mm transition has rear GND coverage within the explicit 5 µm polygon comparison tolerance. The complete RF net overlaps no foreign rear copper. The rear antenna land is the same RF net and intentionally is not ground. Receiver and diode RF pads are fully ground-backed.
- All **561 non-pad transverse samples**, at maximum 0.025 mm pitch, meet receiver-connected front ground on both sides. Minimum first ground intervals are **0.199 mm west** (nominal 0.20 mm) and **1.324568 mm opposite**; largest first gap is **0.175432 mm**. Six nearby plated ground joins connect these returns. These finite guards are not two continuous solid planes and do not establish 50 Ω impedance.
- C1, C2 and R2 retain inherited 0.5 mm thermal neighborhoods and real empty relief sectors in saved copper. Their pad-edge distances to the new solid zone are 1.512, 0.798 and 1.087943 mm. R25.2 is the sole inherited GND pad intentionally changed to solid by zone coverage; U3/D3/H1 already had explicit solid overrides.
- SCL and SDA total routed lengths, including their GNSS branches, remain **106.881865 mm** and **95.102558 mm**. Changed route nets are limited to GND, GNSS RF, +SOLAR, LBOOST, VBAT and SC_BAL_OUT.

The unmodified raw screen reports zero acute gaps and zero sharp tips, plus five enclosed seams and five tiny rear copper remnants. [Every residual has an explicit numerical disposition](reports/geometry-disposition.json), exact bounds, and native primitive provenance. Refined maximum inscribed diameters are **0.36 to 4.51 nm**; every remnant disappears under a 5 nm inward offset. These are far below the 2 µm polygon extraction approximation. They are retained in the evidence and are not treated as fabricated copper islands or etch pockets. Consequently, `audit/summary.json` deliberately retains its failed *zero raw candidates* condition; [acceptance.json](reports/acceptance.json) records the bounded final acceptance with those dispositions. This is not a guarantee about an etching process.

Cleanup changes saved copper as well as tiny corners. Compared with the routed pre-cleanup board, front copper adds 0.004902 mm² and removes 0.000083 mm²; rear copper adds 0.019053 mm² and removes 8.079468 mm². The rear reduction is mostly the deliberate solid-zone retreat and restored thermal/minimum-fill behavior east of the RF corridor. The final reference checks above use this final copper, not the earlier fill. [Full delta](reports/cleanup-copper-delta.json); [separate native cleanup scope](../rf/cleanup-scope-review.json).

## Reproduction

Use KiCad 10.0.0 native Python for extraction and a Python environment with Shapely for geometry. Native extraction is read-only; it does not refill or save the PCB. `reproduce.py` defaults to the macOS KiCad Python path and accepts `--native-python` elsewhere. The full native DRC/ERC checks and manufacturer outputs are maintained by the parent review.

From the repository root:

```sh
analysis/.venv/bin/python analysis/v1_1_top_gnss_20261014/independent/verify_evidence.py
analysis/.venv/bin/python analysis/v1_1_top_gnss_20261014/independent/reproduce.py --output /path/to/new/scratch/review
```

Both canonical-project and strict-review-checkout reproduction runs passed; their complete command logs are retained in `reports/portable-reproduction.json` and `reports/strict-portable-reproduction.json`. The output directory must not exist. `--repo` and `--pcb` support another checkout or an exact frozen candidate. The included prior PCB snapshot provides the native comparison baseline; the 158-file manifest verifies 157 active project/library files plus the included strict review project, without duplicating all model files. The wrapper separately checks the preserved canonical user project hash and makes the strict override explicit. Historical absolute paths in raw logs identify the original run, while these commands use repository-relative dependencies. `manifest.json` pins all local evidence, declarations, scripts and dependencies. No canonical CAD or firmware was modified by these checks.

Geometry checks are not an EM model, antenna tuning, solder tolerance or GNSS sensitivity qualification. The upward 48 mm wire and final assembled solar/string geometry still need the documented reception test.
