# Independent review of the bare-board and assembly cleanup

Reviewed frozen baseline `41027a4a5115713016c49e61b76ecb4f4048da79` against combined PCB SHA-256 `c0278f66e3eae9c135da38b97afaa241990706feb0ae730cbd5dc9a1a9ee4603`. The candidate passed the scoped native and fabrication checks. This review does not release the entire board for manufacture or qualify a hand-soldered antenna installation.

The final source PCB hash is `ea78337c91c73d27b813f09f74dd2d2993e5a82d09800362d82c49a0c4f3ed96`. An [independent finalization attestation](finalization-attestation.json) confirms that only whitespace on 21 blank PCB lines and 18 blank lines in each new antenna footprint was removed: all three complete parse trees are exact, and the other 88 CAD/library files are byte-identical. The frozen review evidence above remains applicable; the two PCB byte hashes are deliberately distinguished.

## Scope and electrical result

The [baseline manifest](baseline-manifest.json) pins 87 regular files: five project files and all 82 existing library/model files. All evaluation fills and exports used external scratch copies; baseline and candidate source hashes stayed unchanged.

The [approved scope](approved-scope.json) allows exactly two full-board mask graphics; both-face untenting; zero nominal mask thickness and a 0.33 mm core within the existing 0.40 mm total; deletion of one redundant VSTOR segment; two antennas' metadata, assembly drawings and model references; four corresponding new local footprint/model files; and one named project rule exception. All other board objects and settings are exact.

Both antennas are represented as the straight enamelled copper wire the user actually installs. The LoRa model is the documented 82 mm 915 MHz reference, with a courtyard covering the documented 86 mm option plus an axial margin. The GNSS model is 48 mm. The inherited 0.321 mm model diameter is nominal and unmeasured. Each STEP file differs from the prior straight-wire model only in five axial endpoint coordinates and its filename. Existing model transforms are unchanged. Schematic changes are limited to the matching antenna metadata property values; library tables and all 82 pre-existing library files are exact.

[Native verification](verification.json) confirms all **232 physical pad connectivity sets** are unchanged and there are **zero opens**. The [connectivity inventory](physical-connectivity.json) records the reachable physical pad UUIDs for every pad. Every pad, ordinary via and surviving track polygon is exact. Both new local footprints match their placed pads.

The 0.0113137 mm VSTOR segment `fa277942-2f97-4c70-a150-464479c3b65e` lies entirely within retained segment `bfbfa6f4-1dbe-4095-a771-3fb9a012fb75`: same net, front layer, 0.25 mm width and 45° centerline. Its removal has zero independent polygon residue. Back copper union is exact. Front native union has only 3.19 × 10⁻⁸ mm² of aggregate added/removed numerical boundary residue and no difference beyond a 50 nm boundary buffer. This is far below the saved copper polygon approximation setting; no intended conductor geometry changed.

## Mask and assembly result

The [geometry review](geometry-verification.json) independently parses the **actual exported mask Gerbers**. Their negative mask-file polarity, dark full-board regions and absence of any clear-polarity operation leave zero covered board area and zero covered copper area on either face. The openings extend at least 1.305 mm beyond the complete native board outline. Gerber job metadata preserves 0.40 mm nominal board thickness and records zero thickness for both mask layers.

Both paste programs, the outline and both plated/non-plated drill exports are exact after removing only creation timestamps. No stencil aperture or drilled hole changed. The [export archive](review-exports.zip) contains the baseline and candidate plots and drill files.

Correcting the obsolete spring antenna courtyard to the confirmed wire installation removes the AE1/D1 overlap. The drawn envelope overlap was 3.2732 mm²; the new drawn envelopes have a **0.162 mm gap**. KiCad’s cached courtyard polygons are inset by 0.005 mm per boundary and therefore report 3.23592 mm² prior overlap and 0.172 mm final gap. These two methods agree after accounting for that cache inset. The nearest antenna-pad-to-diode-pad copper gap remains **0.911999 mm**. D1 and both antenna pads retain their positions, sizes, nets and routing. These are CAD clearances, not measurements of solder fillets or wire bending.

## DRC disposition

Every profile was run fresh with KiCad 10.0.0, refilled zones and schematic parity. All have zero opens and the same 11 pre-existing parity findings.

| Profile | Before | After | Explanation |
|---|---:|---:|---|
| Saved project | 55 | 55 | Two old antenna library mismatches, the courtyard overlap and duplicate stub warning removed; four existing solar-label silk warnings become visible with the full mask opening. |
| Retained netclasses, 0.20 mm edge diagnostic | 110 | 110 | Same four-for-four change; no additional copper-clearance finding. |
| Original 0.50 mm edge policy enabled | 91 | 91 | Same four-for-four change. |
| Prior uniform diagnostic | 70 | 449 | Same four-for-four change plus 379 raw mask-bridge findings in this run. |
| Saved project with mask-bridge check re-enabled | 55 | 373 | Same four-for-four change plus 318 raw mask-bridge findings in this run. |

The project changes **only** `solder_mask_bridge` severity to `ignore`: the specified process deliberately has no mask dams. A fully open board necessarily exposes differently netted conductors in a shared aperture. That exception does not alter copper clearance, connectivity, silk, courtyard, or other checks. Every added raw bridge finding was checked to identify one of the two explicit full-board opening rectangles. The raw enabled reports are retained; their representative bridge counts vary between native runs even with identical source hashes and are not used as an invariant pass criterion.

The four retained silk warnings identify the existing solar `+` and `GND` legends versus the full front opening. They remain visible and are listed exactly in [expected no-mask findings](expected-no-mask-findings.json). No unrelated new finding is accepted. The board still has pre-existing fabrication/library/parity findings; this is a bounded review of the current change.

## Reproduce

Run these from the repository root. `prepare_scope.py` checks the frozen component candidate dimensions and identities before writing its exact inventory; `verify_native.py` enforces that inventory on the combined candidate; `check_geometry.py` checks exported coverage and copper/courtyard geometry.

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_bare_finish_20261012/review/prepare_scope.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_bare_finish_20261012/review/verify_native.py --candidate /Users/twarn/Repositories/ai-working/scratch/stratolink-bare-finish-20261012/combined
analysis/.venv/bin/python analysis/v1_1_bare_finish_20261012/review/check_geometry.py
```

The final whitespace attestation is reproducible with KiCad’s Python and `analysis/v1_1_bare_finish_20261012/review/attest_finalization.py`; it checks both frozen 91-file manifests without repeating broad native tests.
