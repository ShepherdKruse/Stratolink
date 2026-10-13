# Green solder mask, no silkscreen

This implements the user's clarified finish intent: green mask on both faces, no actual silkscreen artwork, ENIG exposed copper. The integrated AS7331 candidate has passed the native and actual-Gerber finish checks below. The canonical PCB has not been changed by these scripts; promotion, pilot package verification and supplier CAM review are separate steps.

`build_green_mask.py` requires the expected source PCB SHA-256 and writes a fresh, separate project copy. It records hashes of every copied input/output. Repeating the same command is a verified no-op only if the script, source bundle and output hashes still match. It does not modify source CAD, copper traces, pad copper, net assignments, paste apertures, board outline or component positions.

The patch removes the old full-board mask openings and all F/B.SilkS graphical items from both placed footprints and every active local footprint library. Required text properties move to fabrication layers. The four solar +/- legends become small isolated copper marks with matching mask openings. Empty silkscreen stackup descriptors remain because KiCad requires the complete layer sequence to export valid mask color/thickness metadata; they do not create printed artwork.

Nominal stackup is 0.31 mm FR4, 0.035 mm copper each face and 0.01 mm green mask each face, totaling the existing 0.4 mm nominal board thickness. These are design metadata, not a claim of supplier coating tolerance.

## Local aperture corrections

Re-enabling `solder_mask_bridge` at error severity exposed 39 problems in the inherited openings. They are resolved by geometry rather than suppressing checks:

- U2/U3 pad mask margins change from +0.102 mm to zero. Their neighboring pad gaps are nominally 0.30 mm; the inherited expansion left 0.096 mm mask webs, below the 0.10 mm green-mask target.
- L1's two rear mask polygons become identical to its existing copper/paste outlines. The inherited +0.10 mm opening growth reached a nearby VBAT trace. Neither the copper nor paste changes.
- Global expansion remains zero; minimum mask web is 0.10 mm and mask-opening-to-foreign-copper clearance is 0.09 mm. Existing U1/U5 special apertures, U7 openings and solar soldering windows are retained.

Ordinary vias inherit tenting on both faces. Tenting does not override a solder-pad window: the old-layout trial has 11 ordinary via centers inside existing component/solar openings, which remain exposed on those faces. U1's five thermal holes remain open within its **rear** exposed-pad window. This is mask tenting, not filling or plugging. Any final via under AS7331 must have both complete copper annuli and hole discs clear of mask openings, with no deposited stencil paste over it.

The [current JLC capability table](https://jlcpcb.com/capabilities/pcb-capabilities) describes 1:1 mask openings, 0.10 mm green-mask spacing and 0.09 mm opening-to-neighboring-trace clearance. Request **Do not modify original solder mask size** and confirm the uploaded aperture geometry in CAM. A blanket +0.05 mm-per-side CAM expansion would not preserve the AS7331 minimum mask webs. Green mask changes RF surface dielectric loading even when conductor geometry stays fixed; pilot RF checks remain necessary.

## Reproduction and evidence

Use KiCad's bundled Python (`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9`):

```sh
python3.9 build_green_mask.py --source <frozen-candidate> --output <new-scratch-copy> --expect-pcb <sha256>
python3.9 verify_green_mask.py --source <frozen-candidate> --finished <new-scratch-copy> --report <native-proof.json>
python3.9 normalize_finish.py --raw <new-scratch-copy> --output <normalized-copy> --expect-pcb <raw-sha256>
python3.9 refill_finish.py --source <normalized-copy> --output <filled-final-copy> --expect-pcb <normalized-sha256>
kicad-cli pcb export gerbers --layers F.Mask,B.Mask,F.SilkS,B.SilkS --output <artwork> <filled-final-copy>/stratolink.kicad_pcb
python3.9 verify_mask_artwork.py --board <filled-final-copy>/stratolink.kicad_pcb --artwork <artwork> --report <artwork-proof.json>
```

`normalize_finish.py` proves native serialization changes only setup property/object order and exact decimal spelling of known geometry fields (for example `.5` to `0.5`); no numeric values, net labels or geometry are ignored. `refill_finish.py` creates another copy, removes stale filled-polygon caches before CLI loading, and runs project-bound `drc --refill-zones --save-board`. Its proof permits only filled-polygon changes and requires 0 DRC/parity issues. All previous snapshots remain frozen. Export the saved final copy, never a stale raw fill.

`verify_green_mask.py` independently compares every footprint and active library, preserving all non-finish geometry and checking native apertures/tenting. `verify_mask_artwork.py` strictly parses KiCad's polygon mask output and rejects unsupported commands; it checks solar/thermal-pad exposure and final under-U6 via-annulus clearance against actual Gerber regions.

Trials 2 and 3 passed native DRC with **0 violations, 0 opens and 0 parity issues**. Trial 3 keeps identical aperture geometry and corrects KiCad stackup metadata; its native/artwork proofs are `trial3-verification.json` and `trial3-artwork-verification.json`. These earlier LTR390 trials are retained as finish regression evidence.

## Final AS7331 candidate, 2026-10-13

The immutable finished project is `~/Repositories/ai-working/scratch/stratolink-release-20261012/as7331/final-green-filled/`. Its PCB SHA-256 is `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`; the final label-corrected schematic SHA-256 is `a06740b35d07d7b81999f7ace2a7a7ff02e185ca3e46a664630bd4bbd00c54b7`.

- Source candidate `fdf54d97…` → raw finish `00b5432b…` → native normalized `869a9f77…` → saved filled board `9d63500a…`.
- All 68 placed footprints and 67 active local footprint libraries were independently checked. Non-finish routing, pads, paste, nets, outlines and zone settings remain exact, except the four intentionally added isolated solar copper markings.
- Saved refill first removed 59 stale filled-polygon records. Project-bound CLI DRC then passed with **0 violations, 0 opens and 0 parity issues**. The refill proof allows only filled-polygon cache changes; native net assignments remain exact.
- Actual mask artwork contains 184 front and 92 rear selective regions, with empty front/rear silkscreen. Solar soldering windows and U1's five rear thermal holes remain open.
- Every via whose annulus intersects U6's maximum 2.7 × 3.75 mm body envelope retains mask over its complete copper annulus and drill disc on both faces. Front mask beyond the 0.25 mm annulus radius is **0.140512 mm** for the corner GND via at `(73.025, 35.100)`, **0.400 mm** for +3.3V at `(74.025, 36.850)`, and **0.175735 mm** for SCL at `(73.800, 38.050)`; rear margins exceed 0.81 mm. The corner via's center is outside the body, but part of its annulus overlaps the package envelope; the selection explicitly includes this case. These are nominal artwork margins, not a claim about actual tent integrity.
- The manufacturing generator's separate green-finish gate verifies 0.01 mm Green mask each face, ENIG, 0.4 mm total, no native silk and selective exposed solar lands.

Evidence: `final-raw-patch.json`, `final-raw-verification.json`, `final-normalization-proof.json`, `final-saved-refill-proof.json`, `final-saved-refill-drc.json`, `final-artwork-verification.json` and `final-green-gate.json`. `final-evidence-hashes.json` fixes the scripts and evidence hashes. The first `final-green-raw` snapshot was superseded when the schematic label correction changed the input bundle; all final proofs use `final-green-raw2`. Raw snapshots remain separate and unchanged. Pilot stencil/package verification and supplier CAM acceptance are still separate requirements.

`test_green_gate.py` verifies the generator gate independently against actual exports. The initial rectangle-only check falsely accepted a restored full-board opening after KiCad rounded its corners; the corrected gate rejects both native and Gerber-only versions. Nine negative cases cover this regression, unsupported Gerber operations, wrong mask color, printed silkscreen and covered solar pads. `green-gate-negative.json` preserves the original failure; `green-gate-test.json` records the fix.
