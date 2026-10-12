# Independent microphone-removal scope

Baseline: Git `38de8d7`, frozen in `baseline/` before changes. The baseline native KiCad netlist confirms the following electrical scope.

| Remove | Reason |
|---|---|
| MK1 / T3902 | Microphone; pad 1 DATA/PDM, pad 4 CLK, pad 5 +3.3 V, pad 2 SELECT and both pad 3 grounds to GND |
| R20 / 33 Ω | Exclusively the series clock connection between U2.32 / PB3 and MK1.4 |
| C13 / 100 nF | Local bypass beside microphone; preserve continuity of its shared supply routing when removing its pad |
| CLK, PDM, Net-(MK1-CLK) copper | Eighteen dedicated front-layer segments; no signal vias |
| Mic-only GND fanout | Eleven segments and the via at (56.084785, 54.024365) |

The entire MK1 footprint includes the 0.5 mm NPTH acoustic hole at (56.0985, 55.643), the explicit front-mask opening and pad masks, solder-paste polygons, courtyard, and model. Delete the footprint rather than only setting DNP; those fabrication objects must disappear with the component.

Preserve the shared ground via at (59.209, 54.46) and its continuation toward (59.877, 55.128). The microphone's +3.3 V copper also feeds FB1 (GNSS supply). Removing C13 opens a small break between (58.1705, 53.569) and (58.3055, 53.434); explicitly reconnect or reroute the continuous supply rail. The ferrite must remain connected to all other retained +3.3 V nodes.

Schematic removal includes MK1, R20, C13, power symbols #PWR033/#PWR034, the local wires/junctions, all four CLK/PDM global labels, and the Mic caption. U2.31/PB4 and U2.32/PB3 become intentional no-connects. Other symbols and nets should remain unchanged.

`check_removal.py` independently checks full retained-footprint content, unchanged schematic symbols and retained netlist nodes, unchanged board graphics, absence of mic signal copper, physical isolation of newly NC MCU pads, and native KiCad connected-pad sets for every retained pad. This includes the shared GNSS supply and every TMP117 connection. Zone refill and comparative DRC/drill/mask checks are additionally required before presenting the result.
