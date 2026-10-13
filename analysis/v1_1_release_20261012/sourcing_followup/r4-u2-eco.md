# R4/U2 sourcing ECO — scratch candidate

The candidate changes only R4/U2 sourcing metadata from canonical checkpoint `1cac1bb0777a4aa3d1048480e9deb55688b0b118`. It does not change the UV sensor or canonical hardware. Manufacturer compatibility is documented in [the RAK review](../radio_sourcing/README.md) and [R4 equivalence review](../radio_sourcing/r4-equivalent.md).

| Reference | Previous exact part | Candidate exact part | Preserved |
|---|---|---|---|
| R4 | UNI-ROYAL 0402WGF3654TCE / C2766827 | YAGEO RC0402FR-073M65L / C477700 | 3.65 MΩ value, 0402 lands, nets, location and rotation |
| U2 | RAK3172-9-SM-NI / C18548052 | RAK3172-8-SM-NI / C5452091 | Existing 32-pad module footprint, pin types, all wiring, center and rotation |

The PCB, schematic and two frozen footprint copies receive matching manufacturer, MPN, LCSC/Supplier Part, description and datasheet fields; U2 Value/MP also change to the exact new orderable. U2 description/datasheet updates are mirrored in the embedded and frozen generic symbol. Imported `Availability`/`AVAILABILITY` strings are cleared instead of encoding temporary stock. The shared generic R4 resistor symbol is unchanged. No pads, outlines, filled copper, routing, electrical values, pin functions, field positions, masks, paste or 3D models change.

Candidate: `/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/sourcing-followup/r4-u2-candidate`.

| File | Candidate SHA-256 |
|---|---|
| PCB | `8e2f83797dd68195aa71b73fc252fe57e53ccd3683ef5f74739dc4d25d6ce8d5` |
| Schematic | `5787cc81a517b45469ea6a801b1ce1232aa7ef681b7b7e208ac7de2e7b754335` |

[The build audit](r4-u2-metadata-build.json) records all five changed files and each allowed property change. Whole parsed-tree equality after applying only those declared property values proves the scope. All 160 protected canonical inputs retain their original hashes.

[Native DRC](r4-u2-drc.json) reproduces the exact four existing silk warnings and has zero opens, parity or footprint-library findings. [Filtered ERC](r4-u2-erc.json) is zero. [Verification](r4-u2-verification.json) compares native exported net names, every pin membership and every pin type against the existing package; all are identical.

The fresh scratch export is at `/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/sourcing-followup/r4-u2-exports`. It has 56 assembly references, 30 part groups and 10 exclusions. Only the R4/U2 BOM identities change. The reviewed CPL and rotation profile are byte-identical to the existing package; CPL SHA-256 remains `eb8ef43bb3b1a6ee0b1efc3f3c1280f519686b6ba1fda44e61ace8cc6c4d1069`. Native positions change only U2's Value string. All nine Gerbers, both drill files and the Gerber job are identical after removing only native creation timestamps. The fresh fabrication ZIP consequently has different bytes; do not call it byte-identical to the already uploaded ZIP.

Reproduce in a new external scratch directory:

```sh
python3 analysis/v1_1_release_20261012/sourcing_followup/build_r4_u2_eco.py \
  --source hardware/pcb \
  --output /absolute/new/scratch/r4-u2-candidate \
  --report /absolute/new/scratch/build.json

/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
  analysis/v1_1_release_20261012/manufacturing/generate.py \
  --candidate /absolute/new/scratch/r4-u2-candidate \
  --output /absolute/new/scratch/r4-u2-exports \
  --allow-part-change R1 --allow-part-change R4 --allow-part-change U2 \
  --supplier-rotation-profile analysis/v1_1_release_20261012/jlc/supplier-rotation-profile.json
```

The builder intentionally requires source hashes matching checkpoint `1cac1bb` and an output under `~/Repositories/ai-working/scratch/`; it will reject a changed canonical source. Native verification uses `pcb drc --schematic-parity --refill-zones --format json` without `--save-board`, and `sch erc --format json`. `verify_r4_u2_eco.py` reproduces the checks against this frozen candidate and report set.

Before promoting or using the new BOM, confirm the actual C5452091 supplier model orientation in the assembly preview. Matching CAD and the prior CPL do not establish a replacement supplier model's orientation. The radio's existing temperature limitations and physical pilot requirements remain; the supplier's generic family description does not establish a −40°C rating for the selected base module. This report does not resolve U6 availability or authorize an order.
