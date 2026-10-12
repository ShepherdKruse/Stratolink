# Canonical hardware project promotion

On 2026-10-12, the user requested that v1.1 continue directly in the Git-tracked project open in KiCad, rather than a separate version-named CAD directory.

The working project is now [hardware/pcb/stratolink.kicad_pro](../../../hardware/pcb/stratolink.kicad_pro) on branch `alpha/hardware-v1.1`. The branch was created from `f0fe2a060b50d3df19777e43e43ab3eb63cfbb47`; that commit preserves the original v1 CAD. Future v1.1 edits belong in `hardware/pcb/`. The old `hardware/v1.1/` draft is superseded.

The canonical PCB is byte-identical to the verified draft. The schematic and project configuration restore the original `stratolink` project basename; the board title/revision remains v1.1. The corrected TMP117 local symbol and project library tables were copied alongside the CAD. All other existing footprint/model library files already matched and were left in place.

Fresh checks on the canonical paths:

- [Independent electrical check](electrical_check.json): pass; all six ball assignments, symbol/netlist agreement, actual MCU/C12 copper connectivity, zero unconnected items. All 62 footprint placements and 239 pad geometries agree with the frozen v1 Git revision.
- [Refilled project DRC](drc-project.json): 78 findings, with the same categories and severities as the verified draft; zero unconnected items and 11 inherited parity warnings.
- [Schematic ERC](erc-project.json): 56 findings, with the same categories and severities as the verified draft.

This promotion adds no further circuit changes. Existing fabrication findings and physical pilot checks remain in [the canonical checklist](../../../hardware/pcb/TODO.md).

The electrical checker now reads the v1 baseline from its fixed Git commit instead of assuming that the working `hardware/pcb/` files are still v1. It is a regression check for this initial TMP117-only change; later intentional placement changes require a corresponding review of its geometry assertions.

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_implementation_20261012/review/check_electrical.py
```
