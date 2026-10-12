# Independent solar-attachment review

**Pass for electrical connectivity and change scope** on candidate PCB SHA-256 `e502e2735535fe525f9699972b2be0dfbc038ae7773fc8da4003339f8e522ba0` and schematic `2833960f4a399552ddb1b599813fc13883012045a820f71018b1a4f9c8f47738`, reviewed October 12 against microphone-removal commit `1aed52ff7af3d27aef6ff4b0ceba710c57dc6865`. The reviewer did not edit candidate or canonical CAD. The parent task subsequently promoted these exact checked hashes to the canonical `hardware/pcb/` project; [promotion manifest](final/promotion.json).

The [independent native checker](check_solar_attachments.py) uses KiCad 10.0.0 and compares the entire footprint structures of every retained component. [Machine-readable evidence](candidate/comparison.json) records:

- All **57 footprints other than J1/J2 are exactly unchanged**, including TMP117 U5, its corrected pad nets and geometry, GNSS, radio and the rear capacitor. Total component count remains 59.
- All **219 schematic pin/net entries are identical**, including pin functions and electrical types. J1/J2 preserve pin 1 `+SOLAR` and pin 2 GND. Their changed metadata does not alter electrical structure; all other schematic symbols, library symbols, wires, labels, no-connects and graphics are unchanged.
- All **230 physical PCB pads** retain the same connected logical node set as the baseline. Each front and back ground land is checked separately: all four connect to the original **67 GND nodes**. Each positive terminal connects to the original **six +SOLAR nodes**. This detects a disconnected face even if another same-number pad remains connected.
- Native KiCad reports **zero unconnected items**. The removed microphone's U2 pins 31/32 remain explicitly unconnected, with no connected copper items.
- The outside extent remains **23.360 × 57.298 mm**, with one valid outline. The two old side holes are removed; the two top suspension holes remain. The new notches are part of the outer perimeter.
- No pre-existing board text or non-outline board graphics changed. The only added board text is **GND twice and + twice** on front silkscreen. No schematic text was added or removed.

The checker was first run against the unchanged baseline using `--allow-baseline-outline` to establish that its strict comparisons work on this design. Final candidate review does not use that option. Frozen baseline CAD is stored only under `~/Repositories/ai-working/scratch/stratolink-solar-review/baseline/`; large baseline CAD copies are not added to the repository.

The native DRC result and enabled-clearance diagnostic remain separate evidence owned by the layout review. Passing connectivity does not clear inherited DRC findings, prove panel fit or solder strength, or constitute manufacturing release.

## Exact candidate mass delta

After the electrical check passed, native KiCad extraction was rerun on that same frozen candidate. [Candidate geometry](candidate/geometry_native.json) and [mass comparison](candidate/mass_comparison.json) use the exact same material assumptions as the [baseline thickness model](../materials/README.md); its original sweep and plots were preserved.

| Modeled bare PCB, 0.4 mm nominal | Baseline | New attachment layout |
|---|---:|---:|
| Net laminate area after all holes | 1298.451 mm² | 1301.195 mm² |
| Front copper area | 632.920 mm² | 631.734 mm² |
| Back copper area | 799.666 mm² | 784.442 mm² |
| Nominal bare-board mass | 1.2546 g | **1.2513 g** |
| FR4-density-only range | 1.2145–1.2948 g | 1.2111–1.2916 g |

The modeled difference is **−3.28 mg**, effectively unchanged at this level of uncertainty. Removing the old support holes adds some laminate; the notches and rerouted/repoured copper offset it. Solder, panel film, support wires, adhesives, surface finish and components are excluded. This is a nominal CAD/material estimate, not a physical weighing or a claim that the completed mount saves 3 mg.

## Reproduce

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_solar_attachments_20261012/review/check_solar_attachments.py --board /absolute/path/stratolink.kicad_pcb --schematic /absolute/path/stratolink.kicad_sch --outdir /absolute/path/review-output
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_solar_attachments_20261012/materials/extract_native.py --board /absolute/path/stratolink.kicad_pcb --output /absolute/path/candidate-geometry.json
analysis/.venv/bin/python analysis/v1_1_solar_attachments_20261012/materials/compare_candidate_mass.py --geometry /absolute/path/candidate-geometry.json --output /absolute/path/candidate-mass.json
```

The checker and extractor confirm the source hashes have not changed during review. Candidate extraction requires an explicit output path and refuses to overwrite the baseline geometry file.
