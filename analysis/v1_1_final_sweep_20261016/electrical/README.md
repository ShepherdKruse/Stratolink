# Final electrical sweep, 16 October 2026

The repaired source passes a fresh KiCad 10.0.0 check with the authoritative reviewed rules: **0 DRC violations, 0 open connections, 0 schematic-parity findings and 0 unexcluded ERC findings**. The two documented TMP117 ALERT and LIS2DH12 SA0 ERC exclusions remain visible in the report. A separate graph of native filled-copper geometry finds no foreign-net overlaps, disconnected pad nets or unanchored assigned-net copper.

| Source | SHA-256 |
| --- | --- |
| Repaired PCB | `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13` |
| Preserved current schematic | `092ddb3451545cc6f7d7d64d8c02c933e89a40acb6897d865e3a8936d54e21fb` |
| Repaired current project | `c9be5b22927d7fe889188023e69f6e774e808aa79d4ea13eb1b2ddc348ffe2f9` |
| Authoritative rules project used in scratch | `915d9f9c4bc8c1eb0866031bf765ff08dc41a7b5bea4fb158ca26c1032ef93cd` |
| Custom rules | `071d900e34c4eb3d3f91003cc0698e261e7fe23beea7107c4db50a1bf60a5136` |
| Previous frozen PCB | `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f` |
| Initial live PCB with missing segment | `01bc0ba752b88678f9ee01fbc2c173c7eaedded96f983bcd0f6df5ea971c95e3` |

The frozen baseline was captured from commit `a146a174d5bbb49c61890e4a17ce455ca31b1f70`. Initial and repaired captures each cover 166 manufacturing inputs. Checks operated on scratch snapshots, and the repaired source files were unchanged at the end of this review. Native refill/save reproduces the repaired PCB hash exactly.

## Defect found and bounded repair

The initial live PCB genuinely failed continuity. Rear VSTOR segment `56e63bbd-ec8b-4f4e-ad43-a47451d11e0e` was missing between `(55.4, 52.1234)` and `(56.78, 53.5034)`. Native DRC reported one missing connection and two dangling ends. The independent pad-connectivity check isolated **R22 pin 1** from U1 pins 3/6/19, C3.1, C4.1 and J4.2.

R22 is the upper 1 MΩ resistor in the PA10 voltage-sense divider. Its removal breaks that measurement path; the main storage rail and the separate VBAT midpoint-balancer supply remained connected. Restoring the original 0.20 mm B.Cu segment was sufficient. `source-scope.json` proves that this was the only repair to the captured live PCB. Relative to the frozen PCB, every source node is now identical except five footprint field-visibility settings on fabrication layers. Footprint placement, pad geometry, routing, zones, fills, outline and models are unchanged.

Three project changes restored the intended checks: solder-mask bridges changed from ignored to error, mask-to-foreign-copper clearance returned from 0 to 0.09 mm, and an obsolete LTR390 ERC exclusion was removed. All other current project settings were preserved. The project difference is recorded in `project-diff.json`; the obsolete exclusion is absent from the authoritative scratch checks.

## Circuit and pin checks

The user's schematic rearrangement changes no circuit definitions: all **66 components, 59 named nets and 247 pin/net/role entries** match the frozen schematic, including exported library-part definitions. All **68 footprints and 259 physical pads** retain their assignments and positions. Known XML slash escaping and the PCB-only H1/H2 ground pads are explicitly classified, with no unexplained mismatch.

`focused-net-check.json` verifies 84 pin assignments and their physical same-net connections across seven groups:

- **TMP117:** the TI YBG top-view ball map is A1 SDA, A2 SCL, B1 V+, B2 GND, C1 ADD0 and C2 ALERT. Native symbol functions and placed pad nets agree. B1 receives 3.3 V; B2/C1/C2 connect to ground.
- **Storage and sensing:** VSTOR reaches the BQ25570 pins, storage bypasses, J4.2 and the restored R22 input. The PA10 divider remains R22/R23 at 1 MΩ each.
- **Midpoint balancer:** TLV8801 output and negative input share SC_BAL_OUT before the 22 Ω isolation resistor. The positive input receives the equal 4.75 MΩ divider, and the output resistor reaches the capacitor midpoint. Supply and bypass are on VBAT.
- **Programming:** standard 32-pad RAK3172 SWDIO/SWCLK/reset map to J20 pins 2/4/3, with reference supply at 1 and ground at 5. The standard-module manufacturer table was checked, rather than the different RAK3172-F package.
- **I2C:** SDA/SCL reach the expected MCU and sensor pins. The external pull-ups remain one 4.7 kΩ resistor per line; the GNSS branches use their existing zero-ohm links.
- **GNSS UART:** TX reaches the GNSS receiver through R16, and GNSS TX reaches MCU RX through R15, both 33 Ω. J4 exposes those same nets.
- **RF feeds:** the LoRa net contains AE1, D1 and U2.12; the GNSS net contains AE2, D3 and U3.11. No unexpected schematic member or physical disconnect was found.

The usual bench qualifications remain: BOOT0 has a 0 Ω ground strap; J20 is the SWD connector. An external transmitter on the GNSS UART can contend with the active GNSS output. U6 remains present in the complete design and intentionally absent from the pilot assembly population. These checks do not measure I2C rise time, RF performance, thermal behavior or balancer dynamic stability.

## Evidence and reproduction

- `capture.json` and `repaired-capture.json`: exact source identities and snapshot locations.
- `current-strict-drc.json` and `live-comparison.json`: the captured defect.
- `repaired-strict-drc.json`, `repaired-strict-erc.json`: fresh final native gates.
- `repaired-comparison.json`: netlist, component, pad and physical connection comparison.
- `repaired-copper.json`, `repaired-physical-copper.json`: independent filled-copper graph.
- `source-scope.json`, `focused-net-check.json`, `summary.json`: bounded edit proof and conclusions.
- `commands.json`: exact native commands, input paths and expected exit codes.

Run `review_semantics.py --scratch SNAPSHOT_ROOT` with KiCad's Python to repeat the pin and source-scope checks. The comparison uses `analysis/v1_1_engineer_review_20261015/connectivity/compare.py`. The physical graph uses `analysis/v1_1_peer_review_20261014/digital/extract_rf_reference.py` followed by `analysis/v1_1_engineer_review_20261015/connectivity/physical_copper.py`. All output paths for a rerun should be fresh; retain this evidence.

ERC was deliberately run with exclusions included, so its process exit code is 5 for the two explicitly excluded warnings. This is not an unexcluded ERC failure. Seven pre-existing DRC categories remain ignored; their exact names are in `capture.json` and the native reports. The independent graph's zero-orphan result applies to assigned nets, not decorative unnetted logo fragments. Factory CAM acceptance remains separate.
