# TMP117 ECO independent electrical review

Review scope: the TMP117 correction starting v1.1, retaining the existing sensor,
0.4 mm-pitch footprint, 3.3 V supply, shared I²C bus and 7-bit address `0x48`.
This review does not release the rest of the board for manufacture.

## Source requirements

The independently checked manufacturer source is TI TMP117 datasheet
SNOSD82D (September 2022), cached at
`../../v1_1_layout_20261012/pcb_audit/sources/tmp117.pdf`.
Its Figure 5-2 and Table 5-1 are explicitly the **top view** of the YBG DSBGA
package used by exact orderable TMP117NAIYBGR.

| Ball | Function | Required board net | KiCad electrical type |
| --- | --- | --- | --- |
| A1 | SDA | SDA | bidirectional |
| A2 | SCL | SCL | input |
| B1 | V+ | +3.3V | power_in |
| B2 | GND | GND | power_in |
| C1 | ADD0 | GND | input |
| C2 | ALERT | GND, or intentionally unconnected | open_collector |

Retaining grounded ALERT is valid: §8.2.1 explicitly permits this unused
open-drain output to be left floating **or connected to ground**. Grounding ADD0
selects `0x48` per Table 7-1, matching `I2C_ADDR_TEMP` in current firmware.
There is no need for a pull-up on the unused grounded ALERT output.

C12 is the existing 100 nF bypass between +3.3V and GND. TI §§8.2.1 and 9
require this bypass as close as practical to supply/ground. Its existing
center is approximately 2 mm from U5, so retaining it is reasonable with a
short local supply path and a short ground return. Changing the sensor to a
thermally isolated island is a later measurement-quality change, not a
prerequisite to correcting the ball assignments.

The footprint copper lands are 0.23 mm diameter at 0.40 mm pitch. Adjacent
different-net lands therefore have 0.17 mm edge clearance by construction.
A 0.20 mm blanket clearance cannot be met inside this package. A documented
local rule of 0.15 mm can accommodate its lands while providing more margin
than the fabricator's 0.10 mm track/space floor. Short radial escapes should
leave the ball grid without routing between adjacent lands. Preserve the
existing separate mask and paste aperture graphics unless a manufacturer
land-pattern review explicitly changes them.

## Release checks for the change

1. The corrected project-local symbol and schematic-embedded symbol agree
   with all six manufacturer ball functions and electrical types.
2. A fresh KiCad schematic netlist and the board independently agree with
   the table above; no old ball assignment survives in placed pad metadata.
3. Copper connects B1 to C12's +3.3V pad, B2/C1 to ground, and A1/A2 to the
   shared SDA/SCL network. No stale track from the old pin map touches a
   new different-net pad or leaves a disconnected copper stub.
4. DRC runs after a zone refill. Review local clearances, new vias, unused
   pad behavior, shorts, and unconnected items. Distinguish pre-existing
   whole-board violations from changes caused by this ECO.
5. Review the actual fabricated copper, solder-mask and stencil apertures
   around U5, including pad orientation and A1 indication.
6. On the first assembled pilot, inspect assembly orientation, test for
   shorts, verify 3.3 V at the bypass, read TMP117 device ID register `0x0F`
   as `0x0117` at address `0x48`, trigger a conversion, and compare stable
   readings against a reference. Device ID alone does not prove temperature
   calibration or ambient-air accuracy.

Exact TMP117NAIYBGR is the N accuracy grade: ±0.2 °C maximum from −40 °C to
+100 °C. Its chip accuracy must not be presented as the assembled payload's
ambient-air measurement accuracy.

## Implementation verdict

**Pass for the bounded TMP117 electrical correction** in
`hardware/v1.1/stratolink-v1.1.*`, checked 2026-10-12. This is not a
whole-board manufacturing release or a physical qualification result.

The independent [checker](check_electrical.py) exported a fresh schematic
netlist, checked every ball against the manufacturer map, and traversed
KiCad's actual copper-connectivity graph. All six balls pass across the
project-local symbol, embedded symbol, schematic netlist, placed-pad net,
placed-pad function and electrical type. In particular:

- A1 reaches the MCU's SDA pin U2/10; A2 reaches SCL U2/9.
- B1 reaches the positive 100 nF bypass terminal C12/2.
- B2, C1 and intentionally grounded C2 reach C12/1 ground.
- The complete board has zero unconnected items.

This is a physical-connectivity check rather than a name-only comparison:
the checker mechanism was independently challenged by removing an escape
track from an in-memory copy of v1, which changed the affected pad's reachable
item count from 81 to 1. That experiment was never saved to CAD.

The final routing uses 0.15 and 0.25 mm new tracks and four ordinary
0.60 mm diameter / 0.30 mm drilled vias. An initial top SDA-via hole-clearance
issue was caught during this review and corrected by rerouting the neighboring
SCL bend. It is absent from the final DRC.

The [electrical check result](electrical_check.json) also proves that all
62 footprint positions, rotations and board sides, all 239 pad geometries,
and all non-U5 pad-to-net assignments are unchanged. Original v1 PCB,
schematic, project, BOM and CPL hashes still match the frozen audit sources.

The enabled-clearance differential screen at 0.15 mm has the same violation
counts and no new violation in the changed sensor area. Its five clearance
findings concern unchanged U7 lands, R23/VSTOR, and J2; the original-project
DRC retains 78 violations, 11 inherited schematic-parity findings, and zero
unconnected items. One remote +SOLAR track is reported against a different
unchanged Edge.Cuts object between diagnostic runs; both board-edge conflicts
are outside this ECO. Whole-board findings remain in the roadmap.

Pending physical verification: fitted orientation, supply/short checks,
direct device-ID and temperature reads, cold behavior and reference
comparison. No measurements were performed on an assembled v1.1 board.
