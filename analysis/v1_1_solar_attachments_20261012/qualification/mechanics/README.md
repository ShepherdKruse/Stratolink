# Solar mount: dimensions, load paths and first-article evidence

2026-10-12. This is a mechanical demand review of the direct panel-to-PCB joint. It adds no strength rating to the ZachTek film or soldered terminal. The [metrology investigation](../metrology/) found that the product photograph's metric grid supports **94 ±2 × 75 ±1.5 mm**, substantially larger than the earlier 71 × 40 mm illustration. These bounds describe a photo-derived estimate, not a manufacturer's dimensional drawing or manufacturing tolerance. The terminal strip is modeled at 5 mm within a photo-estimated 4–6.5 mm range. Published mass remains **1.76 g per panel**. The calculations below use that mass, uniform developed-area mass distribution, a chosen 140 mm assembly bend radius, a 7 mm straight terminal and 1.5 mm insertion.

**The selected minimal change is a 2.0 mm deep notch and a deliberately straight, centrally attached 0.5 mm positive wire.** The notch provides 1.3 mm nominal bank overlap, up from 0.8 mm, while remaining compatible with the constrained nearby routing. Preserve the 1.0 mm routed width and R0.5 mm tip, keep the whole negative terminal straight, and extend the two upper-bank GND lands and fillets with the insertion depth. The lower bank is not needed as a solder joint. A 2.5–3.0 mm notch would give more leverage but consumes more routed area; those are comparisons, not requirements for this minimal revision. These changes improve the load path. They do not supply the missing terminal peel strength or prove a finished assembly robust.

## The existing shallow notch is the weak geometric choice

The previous nominal depth was 1.5 mm, width 1.0 mm, tip radius 0.5 mm and outside-edge copper setback 0.2 mm. A rectangular terminal seated against a straight bank reaches only to the start of the rounded end. Available bank/copper overlap was therefore `depth − width/2 − outside copper setback = 0.8 mm`. Its rendered fillet was shorter still, approximately 0.6 mm. Filling the notch with more solder does not increase the length of bonded terminal metal, and solder does not wet its unplated FR-4 wall.

For the same root moment, a larger bonded length gives a longer moment arm and reduces an idealized bond-patch bending traction. The following table considers only nominal available length, with both fillets sharing load symmetrically. It is a leverage comparison, not a peel-strength calculation.

| Notch depth | Straight-bank insertion | Copper overlap | Ideal bending line traction relative to 1.5 mm depth |
|---|---:|---:|---:|
| 1.5 mm, previous | 1.0 mm | 0.8 mm | 1.000 |
| 2.0 mm, selected | 1.5 mm | 1.3 mm | 0.379 |
| 2.5 mm | 2.0 mm | 1.8 mm | 0.198 |
| 3.0 mm | 2.5 mm | 2.3 mm | 0.121 |

This scaling follows the ideal linear bond traction `q_peak = 6 M / overlap²`, integrated across both fillets' combined breadth. A flexible film and a peel edge violate the rigid-adherend assumptions; actual edge stress can be concentrated. No solder, film, copper or adhesive allowable has been inserted into that formula. If a moment were resisted by a force pair separated by the entire overlap, its magnitude would be at least `M/overlap`; any smaller effective arm raises the force. The front/rear PCB-face separation is not the relevant lever for bending down along the panel span: the moment axis is along panel width, so insertion length matters.

Across the previously screened 0.8–1.2 mm slot widths, the former 1.5 mm depth provides 0.9–0.7 mm nominal overlap; the selected 2.0 mm depth gives 1.4–1.2 mm. If an independent ±0.2 mm depth error is also screened, the latter becomes 1.0–1.6 mm before any copper-registration or terminal-edge contribution. That is a conservative tolerance screen, not an assertion that all errors independently reach those extremes. A deeper opening must extend the existing copper pad and its clearance envelope; simply cutting farther into the old pad would consume the copper behind the rounded end. The negative strip's usable width and the local routing set the maximum permissible depth. Keep solder and the PCB away from the active cells.

## The larger panel changes demand

The default [model](model.py) uses the selected 7 mm straight terminal, 1.5 mm insertion and 140 mm radius; these are assembly choices, not supplier bend specifications. The straight section exceeds the photo-estimated terminal width, keeping the bend away from the cleaned/soldered strip. With a 94 mm developed span, the panel tip is **87.01 mm out and 26.17 mm down**, and its horizontal center of mass is **44.22 mm out**. A uniform flat panel would be a different load case. The model varies length ±4 mm and radius 95/140/180 mm plus a nearly flat case; that length sweep is an engineering sensitivity wider than the photo-estimation interval, not a manufacturer tolerance.

Those shape coordinates use the outer PCB edge and the upper notch bank as their datum. For statics, the nominal 1.3 mm bonded patch spans 0.2–1.5 mm inward from the edge, so its assumed reaction center lies 0.85 mm inward and the COM lever is **45.07 mm**. The real load distribution need not center there. The lower pad is 30.5 mm below the notch center, or **31.0 mm below the upper bank**. Its average 1.48 mm inset from the outer edge becomes 0.63 mm from the nominal bond center. These coordinate corrections are explicit; the calculation does not resolve an actual solder-joint center of stiffness.

| Assumed gravity-like acceleration | Panel force | Root-only moment |
|---|---:|---:|
| 1 g | 0.01726 N | 0.778 N·mm |
| 3 g | 0.05178 N | 2.334 N·mm |
| 5 g | 0.08630 N | 3.890 N·mm |
| 10 g | 0.17260 N | 7.779 N·mm |

The **5 g case is a suggested engineering screen, not a measured launch acceleration, a user-selected acceptance requirement or a released rating**. A small handling force can dominate these inertial cases: 0.1 N at the modeled panel tip gives 8.79 N·mm, equivalent by moment to roughly 11.3 g of uniformly distributed panel inertia. Preventing finger loads on the film and packaging the assembly without loading the outer terminals can matter more than a small change in bare-board stiffness.

The mass is applied over the entire panel, including the small inserted portion. The model does not include solder or wire weight in the panel force. A uniform line load also does not capture gusts, spin, asymmetric panel loading, out-of-plane handling or contact with a harness. Those are additional prototype cases, not covered by a scalar acceleration multiplier.

## A useful positive wire must carry compression

For a pin at the root `O=(0,0)`, a lower board anchor `B=(−b,s)`, and panel endpoint `P=(x,y)`, a downward load `F` at `x_com` is balanced by a **compressive**, straight, two-force brace:

`C = F x_com L / (x s + y b)`, where `L = sqrt((x+b)² + (y−s)²)`.

A flexible wire in tension pulls in the same moment direction as the downward weight and cannot be credited with this support. The old model's red curved lead is an electrical connection, not the straight column represented here. The current lower-hole separation of 30.5 mm is beneficial; keep that leverage.

The ideal brace attaches at the center of the 5 mm outer terminal, developed station `s=91.5 mm`, centered across the 75 mm panel width. That point lies **84.96 mm out and 24.74 mm down** from the edge/upper-bank datum. The central straight brace to the lower pad is **86.67 mm** long and needs **0.1260 N compression** in the illustrative 5 g case. The length excludes the formed outer hook, PTH entry bends, soldered tails and insulation; it is **not a wire-cutting length**.

| Bare solid copper diameter | Two ideal straight wires | Pinned Euler load, each | 5 g demand / ideal buckling load |
|---|---:|---:|---:|
| 0.4 mm | 0.195 g | 0.182 N | 0.694 |
| 0.5 mm | 0.305 g | 0.443 N | 0.284 |
| 0.6 mm | 0.439 g | 0.920 N | 0.137 |

Euler values use generic copper `E=110 GPa`, density `8.96 g/cm³`, straight pin-ended columns and room-temperature elastic behavior. **These ratios are not safety factors.** Neither wire temper nor its plastic yield strength is specified, and joints, end bends, initial bow and thermal distortion are omitted from the ideal column result. The 0.5 mm pair adds about 0.110 g over 0.4 mm, before tails, solder or coating.

An initial half-sine bow of 2 mm, amplified using the ideal elastic `1/(1−C/Pcr)` approximation, produces screening peak stresses of approximately 131.9/29.3/14.2 MPa for 0.4/0.5/0.6 mm at the 5 g demand. No comparison to yield is made because the actual wire's temper and low-temperature properties are unknown. This identifies 0.4 mm as much more sensitive to incidental bends. Use specified solid conductor stock, form the end bends separately, and preserve the central straight section. A stranded or intentionally slack lead should retain zero credited bracing capacity.

Attach a single stiff lead **near the center of the outer terminal strip**. The old illustration attaches it roughly 19 mm off-center. A central connection minimizes the torsion introduced by one brace; the wider 75 mm panel makes an edge attachment even less attractive. The short turn needed to enter a through-hole normal to the PCB is unavoidable in this topology and adds local flexibility. The model does not silently treat that bend as a perfect column end.

The solderable outer terminal is on the upper panel face. A wire cannot run directly inward below that face without crossing the film. The selected assembly uses a **short formed hook past the free panel edge, then turns underneath into the long straight chord**. Keep the hook centered and give it clearance from the film edge; do not count an uncharacterized sharp edge bearing on the film as a support. Form it before soldering so the fragile terminal does not become the bending fixture. Any coating can stop short of the soldered tail.

That hook transfers force through an offset and can load the outer terminal in peel as well as shear. At the ideal 5 g brace force, a 1–3 mm perpendicular offset adds **0.126–0.377 N·mm** local moment, corresponding to **10.3–30.8 MPa** nominal bending stress in a 0.5 mm wire before curved-bend stress concentrations. The [hook screen](end_hook_screen.csv) is an offset sensitivity; it does not assign the real hook an exact offset, stiffness or yield margin. Do not add that local stress mechanically to the middle-of-span bow stress as if they occurred at the same section. Both must be checked in the real formed lead and terminal joint.

The existing positive drill is 0.7 mm. The recorded finished-hole lower tolerance is −0.08 mm, giving a nominal minimum 0.62 mm. A 0.5 mm bare wire has 0.12 mm diametral room before its own tolerance; pass the bare straight tail through before applying solder. A 0.6 mm wire leaves just 0.02 mm before tolerance or pre-tinning and is a poor fit for that drill. If choosing 0.6 mm, use at least a 0.8 mm nominal finished drill and recheck the annulus and clearance.

## Thermal mismatch is another reason not to overstate the column result

The ideal 0.5 mm wire reaches its Euler load with only **1.78 µm axial shortening**. This is not a prediction that a real assembly fails after 1.78 µm: the film, joint and end bends can move, and the wire can bow and carry some load after the ideal bifurcation. It shows why a straight, unloaded rendering is insufficient evidence of a straight brace throughout temperature changes.

For an 86.67 mm span, 100 µm excess developed wire length can form an approximately **1.87 mm half-sine bow**. The model tabulates 10–500 µm mismatch, with no assumption that the film is rigid or that its CTE is known. Differential expansion may bow the wire, change the panel curve, move the root, or share strain among those parts. The film stack and terminal bond are not characterized well enough to assign thermal stress. Check the actual cold assembly shape and electrical operation instead of multiplying room-temperature Euler load by a speculative temperature factor.

## What can be closed in CAD, and what the first assembly must show

The website photograph can close the approximate overall panel envelope and reveal a longer solder strip than the first illustration. It cannot establish polymer/terminal thickness, solder heat damage, terminal peel strength, terminal-to-film adhesion, wire temper, or the combined cold joint behavior. Those are process/material properties, not missing trigonometry.

Proceed with an explicit assembly geometry: negative strips inward, film seated against one notch bank, two visible fillets wetting the same exposed terminal metal and the front/rear GND lands, curvature starting beyond the terminal, and central positive leads. Set the cleaning/pre-tinning patch to span the actual PCB thickness and expose metal on both faces with enough access for the selected fillets. Do not use the polymer cover as a solder surface. The manufacturer assembly procedure, rather than an invented dwell/temperature limit, should control terminal preparation.

Use the first v1.1 assembly to record a small set of directly relevant facts:

1. Actual bare/prepared terminal thickness, slot fit, insertion depth, soldered length and complete assembly mass. Confirm the coating removal leaves a wettable strip without lifting it.
2. A controlled bidirectional panel load in a broad cradle that does not point-load the cells, with force, lever arm and root deflection recorded. Select the handling/launch envelope explicitly; if using the 5 g screen, state it as the chosen prototype test level. A tip force equivalent in moment does **not** also reproduce the distributed inertial shear.
3. Remaining deformation, cracks, foil lift or changed curvature after unloading. Inspect both root fillets and both outer positive joints. Confirm continuity and solar output under repeatable illumination before and after loading.
4. The same observations after temperature cycling over the intended payload temperature envelope. Observe wire bow and clearances at temperature; the coldest ambient-air estimate need not equal the illuminated panel temperature.
5. Clearance to the capacitor, its terminals, pressure-sensor vent, antennas and nearby conductors throughout the measured flex range. A bare positive structural wire needs separation or a thin insulating coating wherever incidental contact could short the panel.

These checks are the evidence needed to call the finished mount robust. No such physical test has been performed in this analysis. They do not prevent making the CAD specific and ready for a prototype now.

## Reproduce

```sh
python3 analysis/v1_1_solar_attachments_20261012/qualification/mechanics/model.py
```

The command writes the CSVs and [summary](summary.json) in this directory. `--length`, `--width`, `--radius`, `--straight`, `--insertion` and `--terminal` expose the dimension/assembly assumptions. The defaults match the selected 2.0 mm deep notch, 1.5 mm insertion, 7 mm straight terminal, 140 mm radius and photo-derived 94 × 75 mm panel with nominal 5 mm strips. Width is recorded for the envelope but does not enter the gravity moment at fixed total mass; it changes aerodynamic area and out-of-plane behavior, which this model does not solve.

Five checks verify numerical integration of the curved panel's center of mass, the compressive brace's vector moment, diameter-to-fourth buckling scaling, diameter-squared mass scaling and notch-overlap geometry. These are equation/unit checks, not physical validation.
