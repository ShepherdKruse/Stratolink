# Schematic electrical-intent cleanup

The reusable cleanup preserves copper, drills, paste, mask, footprint geometry, schematic wiring and physical net membership. It freezes the exact embedded symbols in `lib/Stratolink_v1p1_Symbols.kicad_sym`, changes only reviewed electrical pin types, adds explicit unused-pin markers, and describes actual power entry with nonphysical PWR_FLAG symbols. It does not refresh symbols from a possibly incompatible external library.

Run after all intended power and U7 changes have been integrated, from the repository root:

```sh
python3 analysis/v1_1_release_20261012/erc/clean_erc.py \
  --candidate /absolute/input/candidate --output /absolute/new/scratch/candidate
python3 analysis/v1_1_release_20261012/erc/verify_cleanup.py \
  --candidate /absolute/new/scratch/candidate
```

Input must be an uncleaned candidate and output must not exist. This deliberately fails on changed reviewed pin maps, unexpected remaining ERC findings, pre-existing exclusions, altered physical net membership, or any source mutation. It accepts additional components such as the forthcoming balancing circuit by freezing their embedded symbols dynamically; it does not assume a component count or rewrite their types. An additional circuit can cause a real ERC issue which must be reviewed separately, not automatically suppressed.

The verification independently compares parsed source/result trees and nine native Gerber layers. All existing schematic instances retain their UUIDs, labels, pin numbers, placement, fields and shape; only library IDs change. The cleanup itself changes existing PCB bytes only within `pintype` fields. A later native refill can reorder objects, assign UUIDs to previously UUID-less metadata fields, and serialize filled polygons. Verification therefore refills separate before/after scratch copies under identical project rules, compares every complete authored object by its UUID, and separately requires every native filled polygon to match exactly. Only pin types and specifically identified auto-assigned metadata UUIDs are excluded from that comparison; polygon point order, physical item UUIDs, pads, tracks, shapes, models, zone definitions and settings remain checked. Schematic wires, junctions, labels and text stay exact. All existing project settings and ERC severity matrices remain identical except the three explicitly documented marker exclusions below. A source snapshot is retained under `erc-audit/before` so this proof survives later changes to the input folder.

Final combined PCB `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15` passes this proof: 20 embedded symbols frozen, 111 retained symbol instances, 233 physical pin/net records, zero filtered ERC, and exactly the three raw findings below. Fresh all-track native DRC reports four retained silk warnings, zero opens and zero parity findings. Eight of nine native artworks are byte-identical after timestamps are removed; B.Cu has native net-group serialization differences, so its before/after hashes are explicitly recorded instead of claiming byte identity. Its authored copper objects and all generated fill polygons are exactly identical. See `final-cleanup-verification.json`. The failed pre-refill DRC remains in external scratch as `erc-audit/drc-before-verification.json`; it is not suppressed or used as the final result. Verification leaves final source hashes unchanged.

The baseline integrated trial (`erc-trial-4`, external scratch) corrects 44 library pin types, adds 16 explicit NC markers and three PWR_FLAGs, and freezes 18 embedded symbol definitions. Independent checks prove all 219 physical pad/net memberships unchanged, nine manufacturing artwork layers identical, zero DRC opens/parity findings, and the same four silk-over-copper advisories. The manufacturing generator also succeeds on this cleaned trial: 51 assembly references, 10 intentional exclusions, and unchanged source hashes. This is a reusable-method trial, not a final payload manufacturing release.

## Electrical types and unused pins

| Symbol | Evidence and interpretation |
|---|---|
| U1 BQ25570 | [TI datasheet](https://www.ti.com/lit/ds/symlink/bq25570.pdf), pin-functions table p4. VOUT/VSTOR are supply outputs; input/switch/control roles follow the table. VBAT is a power input in the KiCad model, consistent with the installed official `Battery_Management:BQ25570` symbol. TI's I/O designation describes charge/discharge energy flow and does not require KiCad's signal-bidirectional classification. Pins 9 and 17 are named NC but TI specifies their grounding through PowerPAD: they remain connected to GND, with no NC marker. |
| U3 MAX-M10S | [u-blox datasheet](https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf), table 10 p9. Supply pins are power inputs and VCC_RF is a power output; UART and other IO types follow the table. VIO_SEL is intentionally open for 3.3 V, SAFEBOOT_N stays open, and unused TIMEPULSE/LNA_EN/VCC_RF get explicit NCs. |
| U4 MS5611 | [Manufacturer datasheet, distributor-hosted copy](https://robu-prod-media.s3.ap-south-1.amazonaws.com/uploads/2019/07/GY-63-MS5611-01BA03-High-Precision-Pressure-Sensor.pdf), p14. Preserve the existing physical map: pins 4/5 are internally connected CSB inputs, pin 6 is unused SDO output in I2C mode, pin 7 is bidirectional SDA and pin 8 clock input. |
| U6 LTR-390UV | [LiteOn datasheet v1.7](https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/LTR-390UV-01_Final_%20DS_V1.7.PDF), pin table p4: supplies, NC, clock input, open-drain INT and bidirectional SDA. |
| AE1/AE2 | Antenna terminals are passive connections, not active input drivers. |

The exact newly marked unused pins are U2: 1,2,13,14,15,16,27; U3: 4,13,14,15,18; U4: 6; U6: 2; U7: 11; J20: 6. Existing U2 NC markers are preserved. Every new marker is checked against a sole-member unconnected net before insertion.

The external solar source is declared at J1.1 (`+SOLAR`) and its return at J1.2 (`GND`). A separate flag at FB1.1 describes power supplied to U3 after the passive filter. It does not invent an active output on the bead. A fourth flag at C5.1 declares the actual harvester/storage reservoir supplying U1.VBAT and, when present, U8. The script requires C5.1 and U1.18 to share the original `Net-(U1-VBAT)` or renamed `/VBAT`, C5.2 to remain grounded, and the expected BQ25570 identity. With U8 present, it additionally verifies TLV8801 identity and C5.1/U1.18/U8.5/C22.1/R24.1 `/VBAT` membership plus U8/C22 returns. A static ERC flag describes the circuit's power source; it does not claim the capacitor is charged at every moment.

The earlier direct conversion of TI's VBAT I/O designation to KiCad `bidirectional` was incorrect. [KiCad pin-type guidance](https://docs.kicad.org/10.0/en/eeschema/eeschema.html#pin-electrical-types) distinguishes signal IO from power terminals, and the [library conventions](https://klc.kicad.org/symbol/s4/s4.4/) require power-pin types for power connections. The installed official `Battery_Management.kicad_sym` models the exact BQ25570 VBAT pin 18 as `power_in`; only that relevant precedent was used, with no library refresh. `power_in` plus the real reservoir flag retains power-source checking and removes the artificial digital-output conflict without adding an ERC exclusion. The failed intermediate report is preserved as `trial-vbat-signal-model-raw-erc.json`: it includes the prior extra U1.18/#FLG104 warning. The final model still has exactly the three grounded-pin exclusions described below.

## Exactly three grounded-pin exclusions

Raw corrected ERC is retained in `trial-raw-erc.json`: **two errors and one warning**. Native default ERC is zero after three exact pin-pair exclusions. `trial-all-erc.json` shows all three as excluded with their rationales. KiCad serializes both error/warning variants with the same `pin_to_pin` key and reloads excluded records with warning severity; the raw report therefore remains the authoritative pre-exclusion severity record.

| Marker | Reason |
|---|---|
| U5.C2 ALERT versus external GND flag | [TI TMP117 §8.2.1](https://www.ti.com/lit/ds/symlink/tmp117.pdf) explicitly permits grounding ALERT when unused. Its open-drain electrical type remains correct. The board cannot use this interrupt output. |
| U6.5 INT versus external GND flag | LiteOn identifies INT as open-drain. Its inherited GND connection has no pull-up or driven-high source, so a sinking output cannot create high-versus-low contention here. This is an electrical inference; an explicit LiteOn recommendation to ground unused INT was not found. The interrupt feature is unavailable and should remain disabled. |
| U7.3 SDO/SA0 versus external GND flag | [ST LIS2DH12 §6.1.1](https://www.st.com/resource/en/datasheet/lis2dh12.pdf) permits the grounded SA0 address selection for I2C (0x18) with CS high. The bidirectional type is retained because this pin also serves as SPI data output. |

Exclusions bind the two pin UUIDs, exact position and sheet paths; there is no blanket pin-to-pin suppression. Serialization follows the [KiCad 10 marker implementation](https://github.com/KiCad/kicad-source-mirror/blob/10.0.0/eeschema/sch_marker.cpp) and [ERC settings implementation](https://github.com/KiCad/kicad-source-mirror/blob/10.0.0/eeschema/erc/erc_settings.cpp). Coordinate conversion uses the [schematic internal-unit definition](https://github.com/KiCad/kicad-source-mirror/blob/10.0.0/include/base_units.h), independently of an observed CLI JSON schematic-position scaling discrepancy.

## Firmware follow-up

`firmware/src/sensor_lis2dh12.cpp` currently does not configure CTRL_REG0. The grounded SA0 pin has a default internal pull-up. ST specifies SDO_PU_DISC in CTRL_REG0 (0x1E) and requires bits 0–6 to retain their default pattern; write/read back 0x90 after startup to disconnect that pull-up, with appropriate firmware error handling and bench verification. See [ST datasheet §8.4](https://www.st.com/resource/en/datasheet/lis2dh12.pdf). This audit changes no firmware and makes no unmeasured current-saving claim.

`firmware/src/sensor_ltr390.cpp` does not configure INT_CFG (0x19), relying on the reset interrupt-disabled state. Explicitly disable/read back LS_INT_EN during sensor initialization and recovery so software intent matches the grounded, unavailable INT output. Do not attempt interrupt-driven operation on this board connection. TMP117 ALERT is similarly unavailable to firmware.

Files prefixed `trial-` are historical method-validation snapshots. The initial trial predates power integration; `trial-vbat-power-model-*` uses a provisional, unrouted power-layout snapshot and establishes ERC behavior only. The updated power-input/reservoir-flag model passes full structural/artwork verification on the existing routed U7/header candidate (`trial-vbat-legacy-verification.json`) and yields zero filtered ERC findings on both variants, retaining the same three exclusions. Regenerate the complete audit for the final candidate rather than treating these hashes or counts as final-board evidence.
