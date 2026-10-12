# Deeper solar notch: checked geometry

The reviewed revision is a **1.0 mm wide × 2.0 mm deep open, unplated notch with an R0.5 mm tip**, retaining the same y54.5 mm center and outer board dimensions. It uses an **upper-bank GND land on both PCB faces**, each 2.1 × 0.68 mm, with one conventional 0.6/0.3 mm GND stitching via per side. The lower bank has no solder land or stitching via. The panel's exposed negative terminal seats against the upper bank; the front and rear fillets wet that same terminal face.

This is a geometry and electrical verification, not a measured joint-strength result. Actual panel film thickness, exposed metal, solder bond quality and flex durability cannot be established from the PCB layout. See the parent qualification record for panel dimensional evidence and assembly limits.

## Improvement and layout constraints

The straight bank grows from 1.0 to 1.5 mm. After the 0.20 mm outside-edge copper setback, nominal straight solder overlap grows **0.8 → 1.3 mm (62.5%)**. The notch-to-copper setback stays 0.22 mm. More geometrical overlap is useful for assembly; it does not imply a 62.5% increase in strength. The old U-shaped land had more total copper area around a part of the notch that did not contact the seated terminal.

The validated revision changes **no signal or ground tracks**, no component placement, and no other footprint. It changes six outline objects and removes the two lower ground vias. The board stays 0.4 mm thick. Nominal board web between opposite notch tips is 19.359 mm. The lower positive contacts remain 1.4 mm round copper lands with 0.7 mm plated drills at (54.8, 85.0) and (75.2, 85.0).

Nearest non-GND copper to the retained rectangular lands remains 0.1985 mm (left VSTOR), 0.2085 mm (left +SOLAR), 0.1755 mm (right VSTOR) and 0.1505 mm (right RX). These are native-polygon distance screens; native DRC is the acceptance check. The 2.0 mm notch is 1.5635 mm from the left C5 courtyard and 1.8055 mm from its right courtyard. The next right-hand courtyards are R15 at 1.9203 mm and U4 at 2.0578 mm. These are 2D layout clearances, not a full external panel/solder envelope.

| Depth | Nominal straight solder overlap | If the previous U-land keeps its 0.8 mm inward extension |
|---|---:|---|
| 1.5 mm | 0.8 mm | Existing geometry; no new conflicts |
| 2.0 mm | 1.3 mm | Left +3.3V, VSTOR, +SOLAR; right PB5, VSTOR, RX, TX need rerouting |
| 2.5 mm | 1.8 mm | Cuts already encroach on VSTOR/+SOLAR left and VSTOR/RX right; extended lands also reach SDA/+SOLAR on right |
| 3.0 mm | 2.3 mm | Additional PB5/TX cut conflicts; C5 courtyard clearance drops to 0.564 mm left |

Simply deepening the old notch but keeping the old U-land envelope would leave only about **0.08 mm of copper around the tip**, so that was rejected. Splitting the U-land into upper and lower rectangles initially seemed to avoid rerouting, but native refill exposed disconnected lower-bank islands. That version was rejected: [recorded DRC](rejected-split-banks-drc.json). Removing those unused lower lands and their vias lets native refill discard the isolated ground islands while retaining both required front/back upper-bank solder contacts.

[Alternative geometry overlay](deeper_notches.png) · [Native copper distance results](screen.json)

## Final native verification

The frozen source is the KiCad board at Git `76ee6e8`; its electrical geometry equals the prior checked `14d94de` board. The final checked scratch directory is `~/Repositories/ai-working/scratch/stratolink-solar-depth2/upper-only/`. The parent task handles promotion to canonical hardware and updates the assembly models separately.

- All **57 other footprints** remain exact.
- All **879 straight tracks and three routed arcs** remain exact. All 142 remaining vias are exact; only the two lower ground stitching vias were removed.
- All **230 physical-pad connectivity checks pass**; each front/back solar ground land reaches all 67 original logical GND nodes. Both positive contacts reach the same six +SOLAR nodes.
- Project DRC: **70 inherited findings, zero opens, 11 parity findings**.
- Diagnostic DRC at 0.15 mm net clearance / 0.20 mm edge clearance: **83 inherited findings, zero opens, 11 parity findings**.
- Every finding signature matches the previous validated reports; no new finding was waived.
- J1/J2 footprint metadata is consistently renamed `Solar_Notch_Left_1p0x2p0` / `Solar_Notch_Right_1p0x2p0` in PCB, schematic and project-local libraries. The schematic has no electrical changes. The project settings and 3D model references are unchanged.

[Exact scope, hashes and DRC comparison](upper-only-verification.json) · [Pad-level connectivity](upper-only-connectivity/comparison.json) · [Fresh fabrication evidence](fabrication/evidence.json)

## Files and reproduction

The four promotion files are `stratolink.kicad_pcb`, `stratolink.kicad_sch`, `lib/Solar_Notch_Left_1p0x2p0.kicad_mod`, and `lib/Solar_Notch_Right_1p0x2p0.kicad_mod`, all beneath the checked scratch directory. Remove the superseded `Solar_Notch_Left_1p0x1p5.kicad_mod` and `Solar_Notch_Right_1p0x1p5.kicad_mod` libraries when promoting. Do not copy scratch model assets or project settings.

`build_scratch.py --upper-only` reconstructs a disposable candidate from the fixed Git checkpoint. Run native refill and the native DRC/connection checks after rebuilding. `verify_candidate.py` is a read-only scope and recorded-report regression verifier; it does not replace native DRC. `extract_copper.py` / `screen.py` produced the read-only alternative study from the pre-change canonical board.

The scripts use scratch paths deliberately and never save canonical hardware. The final export archive contains fresh review Gerbers, drills and SVGs; it is not an order package that waives inherited fabrication findings.
