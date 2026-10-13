# Supplier rule candidate

The old project ignored copper clearance, copper-edge clearance and annular-ring violations. This scratch candidate enables all three, selects the sourced JLC routed-edge minimum of0.20mm, track width/minimum process clearance0.10mm, and a default low-voltage routing target of0.15mm. The original0.20mm net-class screen is retained in `initial-enabled.json`; the board is not an insulation/isolation barrier and all operating rails are below6V. This is a declared manufacturing/design-rule change, not an assertion that historical0.20mm gaps were met.

Fine-pitch pad pairs are handled explicitly: J3/J4 min0.12mm, U7 min0.10mm. R23's two pads beside VSTOR have a named0.13mm constraint: all-track-errors reports reveal0.133mm atPA10 and0.147mm atGND. Component-lead PTH holes require0.18mm annulus and0.28mm hole-to-foreign-copper clearance. U1's thermal pad holes are classified as vias, not component-lead holes. Existing0.10mm via-ring minimum remains enabled.

Source: [JLC capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), inspected2026-10-12; captured rows in `../jlc/capabilities.json`. [KiCad rule syntax](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#custom_design_rules) was checked directly. Both castellations and edge plating require≥0.6mm atJLC, and are excluded from the retained0.4mm design.

`build_rules.py` only writes external scratch, then runs KiCad10 native refill plus all-track-errors DRC and schematic parity. Current baseline with these rules:55warnings, no copper/edge/ring violations, zero opens,11known parity findings. These identity findings are being corrected independently. Full-board no-mask bridge checks remain inapplicable; silk-over-opening warnings remain visible. This is not yet the final release report.

Before promotion, integrate new headers and U7 changes, re-run all enabled checks, and independently compare actual copper, drill/paste/outline and physical connectivity. Neither0.10mm process capability nor a clean DRC provides physical pilot qualification.
