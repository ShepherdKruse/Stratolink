# Electrical comparison of the engineer reroute

Final PCB: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`.
Final schematic: `c772c2a0edff4d6f7616afb0988fc95c2cbb8c2d3572c1429fc0f3718f69e921`.

All listed electrical checks in `summary.json` pass. The final schematic preserves all 66 component definitions, 59 named nets and 247 pin/net/pin-role entries from the prior review. The PCB preserves all 68 footprints, 259 physical pads and 250 logical reference/pin net assignments. Native saved connectivity reports zero opens; each pad reaches every intended same-net pad. A separate polygon graph finds no foreign-net overlaps, disconnected assigned-net pad clusters or unanchored assigned-net copper. Numeric net codes are not used for identity comparisons.

The received board had two isolated ground clusters, GND shorts to PA1/PA9 and nine unanchored ground fill islands. These are repaired in the final candidate. Seven footprint schematic paths and the J1/J2/J20 placement exclusions are restored. The schematic changes after intake are only `in_pos_files=no` on those three connectors. Its earlier KiCad 8 to 10 conversion also annotated an existing power symbol and corrected a duplicate power-pin UUID, without changing the circuit. Existing slash escaping on eight no-connect net labels and the PCB-only grounded suspension holes H1/H2 are explicitly classified in the parity report.

Relative to the engineer's input, C5 is the only moved footprint, shifted 1.30 mm in Y to improve the GNSS rear ground reference. Assembly clearances were verified separately. All other 67 component poses are unchanged. U1's solder-mask openings were restored; L2/U4 mask margins were corrected. The fabrication report records the two local electrical copper-pocket repairs separately. This electrical review does not assess RF performance or mechanical fit.

The right minus at (74.3, 55.0) lies entirely over connected ground. Its nominal mask aperture has 0.08075 mm ground-edge margin and 0.23943 mm distance to foreign-net copper. See `right-minus-ground.json`.

`final-comparison.json` compares the final design to the prior review. `repair-scope.json` compares it to the engineer's intake. `incoming-comparison.json` and `incoming-summary.json` preserve the original findings. `final-copper.json` is native saved-copper geometry; `final-physical-copper.json` records the independent connectivity graph. The graph joins layers only through physical plated pads/vias. It uses positive-area intersections of native nominal land envelopes; drill voids are not subtracted, so overlap areas are screening measures rather than plated-metal measurements.

Reproduce with the same prior/intake bundles and KiCad 10:

```sh
kicad-cli sch export netlist --format kicadxml --output final.xml CANDIDATE/stratolink.kicad_sch
KICAD_PYTHON compare.py --repo REPO --before BASELINE --after CANDIDATE --before-xml baseline.xml --after-xml final.xml --output final-comparison.json
KICAD_PYTHON REPO/analysis/v1_1_peer_review_20261014/digital/extract_rf_reference.py --pcb CANDIDATE/stratolink.kicad_pcb --output final-copper.json
ANALYSIS_PYTHON physical_copper.py --geometry final-copper.json --output final-physical-copper.json
KICAD_PYTHON extract_mask_text.py --repo REPO --pcb CANDIDATE/stratolink.kicad_pcb --output final-mask-texts.json
ANALYSIS_PYTHON check_mask_ground.py --copper final-copper.json --mask final-mask-texts.json --physical final-physical-copper.json --output right-minus-ground.json
```

Source CAD was not modified by these checks. Zero unanchored assigned-net copper is distinct from the intentionally unnetted logo microdetail documented in the fabrication review.
