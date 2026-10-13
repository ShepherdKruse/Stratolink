# Independent review of the assembly population export

The manufacturing generator validates native PCB/schematic part metadata and placement for the complete design before applying an assembly-only omission profile. The pilot policy is **omit U6 only**, bound to the exact approved AS7331 MPN and LCSC identity. R27 and C23 stay fitted. All other retained BOM/CPL fields must match the complete assembly audit.

Two initial parser defects were reported to the root agent and fixed there:

1. Plain `json.loads` silently accepted duplicate keys, including duplicate U6 entries and conflicting MPN/LCSC identities. The new `read_population_profile` rejects duplicates recursively.
2. A supplied JSON `null` profile was indistinguishable from omitting the profile option. The reader now requires a nonempty object. Only an absent CLI option reaches `apply_population(..., None)`.

[The independent test](test_population.py) runs the actual generator functions and passes **34 cases**: exact omission/preservation, wrong MPN, wrong LCSC, missing/numeric identity, empty or missing reason, incorrect schema, wrong reference, stale profile against the legacy sensor or an already-absent U6, whole-assembly omission, explicit null/empty/list/bool/string input, malformed JSON, and duplicate keys at each relevant level. It also checks that accepted and rejected profiles leave the input design and profile data unchanged. [Results](population-test.json).

The generator's generic profile mechanism permits other explicitly named, identity-matched omissions; the release verifier separately enforces this pilot's **U6-only** policy. It does not treat the profile itself as proof of which part was approved.

The same test's `--package` mode verifies the actual package against separately supplied approved MPN/LCSC values. It compares the complete `design_assembly` with the filtered assembly, requires R27 and C23 retained, checks every emitted BOM and CPL field, checks counts and copied profile identity, validates every source/evidence/output hash, and checks that every output is represented in the manifest. It also checks that the profile copy has the exact source byte hash. The final package results are below; no native fabrication or electrical validation is claimed by the synthetic unit cases alone.

Run the unit cases:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/as7331/manufacturing/test_population.py
```

Then bind an exported package to the approved identity (use the exact canonical MPN field, which may include the manufacturer's packaging suffix):

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/as7331/manufacturing/test_population.py --package /absolute/export/path --expected-mpn 'AS7331-AQFM' --expected-lcsc C20482877
```

No generator, CAD, manufacturing export, or supplier order was modified by this review subtask.

## Independent pilot stencil review

[test_stencil.py](test_stencil.py) separately checks the entire parsed source PCB against the stencil copy, allowing only native reordering of UUID-tagged objects and removal of **exactly 16 U6 front-paste flags**. Every other pad/layer, routing object, zone, graphic and parameter must remain equal. This deliberately requires the final canonical candidate to have been saved natively; the early candidate contained unsaved new property metadata that KiCad normalized when making the export copy. The candidate test normalizes only its disposable snapshot; it never saves the working candidate.

The artwork check resolves Gerber D-code numbers to actual aperture definitions and macro shapes before comparing all drawing commands. Full design front paste has **16 U6 apertures**, pilot paste has **zero**, and all remaining front artwork and the entire rear artwork are identical. Unknown transform/drawing commands fail rather than being silently ignored. Candidate testing also rejects missing references, empty/no-op omissions and explicit footprint paste graphics that pad-layer removal would leave behind. [Candidate test results](stencil-test.json).

The package verifier runs this stencil check too, validates every reported changed pad UUID and paste-file hash, and checks that the pilot ZIP actually contains the same two paste files as the reviewed pilot Gerber directory. This prevents a correct audit paired with the wrong stencil in the upload ZIP.

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/as7331/manufacturing/test_stencil.py --candidate /absolute/candidate/folder
```

## Final canonical package verification, 2026-10-13

`hardware/gerbers/v1.1-pilot` passed against canonical PCB SHA-256 `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`:

- **57 pilot assembly references / 58 complete-design references / 11 exclusions.** Only U6 is removed by the population variant; C14, C23 and R27 remain fitted.
- All 166 source hashes, 37 output hashes and recorded evidence hashes are valid. Retained BOM/CPL rows match every complete-design field.
- The stencil copy changes exactly 16 U6 front-paste pad flags. Full-design U6 paste has 16 apertures; pilot U6 paste has zero. All other front and rear paste artwork is identical.
- All 12 ZIP entries exactly match the reviewed fabrication directory, with no duplicate or missing entries.
- The green-finish proof reproduces exactly. Actual package mask geometry equals the independently checked pre-promotion artwork: solar/thermal windows are exposed, silk is empty, and all three vias whose annuli intersect U6's maximum package envelope remain fully covered by mask on both faces.

Reports: [population/stencil](package-verification.json), [actual mask geometry](package-mask-verification.json), [archive and exact hashes](package-archive-verification.json).

Upload archive SHA-256: `6fd6f81550d8a30e163028bc88d30aad88fad6c8391e8dbdbe215322d3bef4e0`. Manifest SHA-256: `4bcf43f2b06c63de17595a4e501104f16c15d2557de24f85ef7bb041851cab81`. These checks bind this exact export; later regeneration requires revalidation. Supplier CAM/placement acceptance remains a separate step.
