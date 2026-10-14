# GNSS feed revision, accepted in CAD

Promoted to `hardware/pcb` on 14 October 2026. PCB SHA-256: `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`. Native checks and independent scope, connectivity, ground-reference and copper screens pass. See [final evidence](final/root-review.json). Supplier CAM and physical RF/assembly tests remain pending. The following records explain the change from the copper-cleanup checkpoint `4fcdb39b`.

## Why this placement

The original approximately 13.44 mm GNSS feed crossed the rear boost switching trace and launched over C5's positive terminal. The rejected western detour was longer and crossed additional rear supply/balancer copper. Moving the receiver instead would place the module over the rear inductor and balance circuitry. The selected candidate keeps the receiver and switching loops fixed, moves the GNSS wire feed toward the left board edge, and shifts the flat rear capacitor moderately right.

The complete artwork matters. An early hole position touched the existing rear copper graphic; native connectivity correctly revealed the resulting unintended RF copper extension. That trial was rejected. The selected feed lies below the existing rear graphic and front lettering. The rear graphic is preserved. The lettering shapes are preserved and translated slightly upward to make room for a grounded guard beside the diagonal feed.

## Intended bounded change

- AE2: `(55.3, 47.85)` mm, rotation 180°. The same nominal 48 mm straight-wire model points left. Its model Z offset rises from 0.15 to 0.25 mm to remove inherited nominal surface penetration; this is an unmeasured assembly bend/standoff. The cut is measured from the feed; trim/tune the completed assembly.
- D3: `(58.0, 45.05)` mm, rotation 270°. Its RF terminal lies directly on the feed, and its ground terminal connects to the adjacent ground area/stitch.
- C5: +1.8 mm in X, with its three electrical terminals and dependent `/VBAT`, `/SC_MID`, `+3.3V`, SCL and GND routes explicitly reconciled. Its flat rear fit, board thickness, solar mounts and receiver position remain fixed.
- RF: 0.45 mm front copper and smooth 0.35 mm radius bends. The main feed is 6.575 mm, 51.1% shorter than the original. Both faces receive local GND fill, connected to the original ground network through native-verified copper and stitches.
- Front guard: a 0.30 mm grounded strip fills the previously missing side of the diagonal feed. STRATOLINK.ORG moves up 0.55 mm and PICO MAINBOARD V1.1 up 0.22 mm, with exact glyph shapes and styling preserved. A stitch at (55.45,46.65) and the D3 return anchor that guard. Independent saved-fill sampling finds ground on both sides at all 144 non-pad sample locations; minimum guard width is 0.300 mm.
- C5 courtyard: derived from the maximum 30.5 by 14.5 mm case and terminal envelope, with a declared 0.125 mm allowance for controlled manual assembly. This is a stated local allowance, not a claimed manufacturing standard.
- U3 ground pads 10/12 and D3 ground pad 1 use solid zone connections. Other pad copper geometry and logical nets are unchanged.
- A fabrication-layer assembly note identifies the new leftward wire exit. No silkscreen is added.

## Limits of the calculation

`cpw_screen.py` uses the board-declared nominal 0.31 mm core, 0.035 mm copper and dielectric constant 4.5. A 0.45 mm strip with 0.15 mm same-side ground gap is approximately 48.48 Ω in that first-order grounded-coplanar model. The illustrative corner range is 41.1–56.4 Ω. This assumes continuous rear reference and idealized side grounds, and excludes the antenna hole, receiver land, ESD package, solder mask and finite board. Those launches are not uniform transmission line. The actual front grounds are finite and asymmetric: the added guard is at least 0.300 mm wide, with maximum sampled gap 0.167 mm; the opposite side is at least 0.635 mm wide, with a larger 0.396 mm gap near a transition. These bounds do not justify applying the infinite-ground calculation uniformly along the entire feed.

Saved-fill projection and native DRC establish copper continuity and separation, not RF performance. Verify the finished antenna with the solar panels, capacitor, suspension and actual wire bend attached. Compare GNSS C/N0, acquisition/reacquisition, satellite geometry and supply/reset behavior against a flown board under comparable conditions. The receiver's existing remote supply filtering and possible converter coupling remain independent qualification concerns.

The nominal wire diameter (0.321 mm), bend and panel shapes are model assumptions. Primary CAP-XX maximum case dimensions are included in the mechanical review, but hand-solder buildup and placement variation still need inspection on the pilots. Do not interpret a nominal model clearance as a measured physical allowance.
