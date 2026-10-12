# Suspension-hole mechanics

2026-10-12. Geometry is extracted from the actual board at `a9d6ed5`; [geometry.json](geometry.json) records its hash and hole coordinates. This is an analytical load/stiffness screen supporting the separate membrane FE comparison. It does not calculate an absolute breaking load, fatigue life or line-abrasion life.

**Keep the two hole centers, reduce the finished holes to 2.0 mm, and use 3.2 mm ground pads on both faces with plated barrels.** Reducing the holes provides the directly calculable extra FR-4 ligament. The copper/barrel provides a potentially useful bonded rim and covers exposed glass at the bore; its contribution to failure load is not known. This is a more economical local change than moving the holes into occupied routing. Retain the 0.4 mm board for this revision and check the actual string on the first article.

## Real geometry and alternatives

The existing cutouts are circles drawn on `Edge.Cuts`, not plated mounting pads. Each is **2.701014 mm diameter**, at `(55.665,31.745)` and `(74.327,31.745)` mm. Each center coincides with the center of its **R2.348 mm** rounded outer corner. Thus the smallest remaining ligament is **0.997493 mm** throughout that quarter-circle. Hole-center separation is **18.662 mm**. The board's CAD stack is 0.31 mm FR-4 core, two 35 µm copper layers and two 10 µm masks, totaling 0.4 mm; actual delivered thickness remains a separate measurement.

| Same-center design | Hole diameter | Nominal edge-to-finished-bore ligament | Approximate FR-4 ligament after barrel drilling allowance |
|---|---:|---:|---:|
| Existing routed hole | 2.701 mm | 0.997 mm | 0.997 mm |
| Smaller unplated hole | 2.000 mm | 1.348 mm | 1.348 mm |
| Selected plated hole | 2.000 mm | 1.348 mm | 1.330 mm |
| Alternative plated hole | 2.200 mm | 1.248 mm | 1.230 mm |

The plated-hole estimate uses 18 µm radial barrel copper, the supplier's quoted **average**, not a guaranteed minimum. The substrate drill must be approximately 36 µm larger in diameter to retain the finished bore. This avoids crediting copper thickness as FR-4. The selected design gives about **33% more substrate ligament**, or 35% when comparing the nominal finished boundaries. A 3.2 mm pad around a 2.0 mm finished bore has 0.6 mm nominal radial copper annulus, before drill and registration tolerances.

Moving the original holes inward **and downward** by 0.3/0.5/1.0 mm per axis would raise the minimum geometric ligament to 1.297/1.497/1.997 mm. Moving only horizontally inward leaves the upward ligament unchanged. For a nonnegative diagonal move `(dx,dy)`, top and side ligaments are `R+dy−r` and `R+dx−r`; the rounded arc is farther away. The [geometry comparison](geometry_comparison.csv) includes all movements for all hole variants.

The independent layout screen finds that the same-center 2.0 mm hole/3.2 mm grounded pad fits without signal or component movement. A 0.3 mm diagonal shift with that pad brings the right-side +SOLAR clearance to about 0.148 mm, below the 0.15 mm screening limit; a 0.5 mm shift overlaps it. Moving is therefore not a free improvement. The smaller same-center hole already recovers more useful material with less electrical/layout risk.

Two complete rings, on both faces, contain approximately **6.15 mg copper**; two 18 µm-average barrels add about **0.81 mg**. The smaller drills recover about **2.91 mg core**, giving a **9.87 mg explicit core/ring/barrel subtotal**. This is not an upper bound on the whole-board change: existing copper overlapping the new pads reduces added copper, while ground refill can add copper beyond the nominal pad perimeter where the old routed-hole clearance is removed. A native union of the complete before/after copper is needed for that total. This accounting excludes finish, soldermask changes and any process change in delivered plating. It is a geometry estimate, not a scale measurement. No metal grommet or solder buildup is included.

## The continuous string triangle pulls inward as well as upward

The user describes one thin stretchy string through both holes, forming a triangle tied to the balloon above. A continuous `apex → left hole → right hole → apex` loop has a bottom segment across the board. That segment adds inward tension at both corners. Treating it as two independently anchored hanging legs misses this force.

For total supported load `W=m g k`, half-spacing `a=9.331 mm`, apex height `h` above the hole-center line, and `α=atan(a/h)`, a symmetric frictionless loop gives:

`T = W/(2 cos α)`

`V_hole = W/2`

`H_hole = T(1+sin α)` inward

`R_hole = sqrt(V_hole²+H_hole²)`.

With two separate tied legs, the inward term is only `T sin α`. Friction, the knot, unequal leg length, cross-board contact and elasticity can make segment tensions unequal; the symmetric loop is the reproducible baseline, not a claim that the actual string slides freely.

For an **illustrative 20 g payload under a 5× load factor**, `W=0.981 N`:

| Apex height | Segment tension | Inward load at each hole | Upward load at each hole | Resultant at each hole |
|---|---:|---:|---:|---:|
| 10 mm | 0.671 N | 1.128 N | 0.490 N | 1.230 N |
| 20 mm | 0.541 N | 0.770 N | 0.490 N | 0.913 N |
| 40 mm | 0.503 N | 0.618 N | 0.490 N | 0.789 N |
| 80 mm | 0.494 N | 0.551 N | 0.490 N | 0.737 N |

Neither 20 g nor 5× is a measured payload/load requirement. Loads scale linearly with actual mass and chosen factor. The [full sweep](bridle_loads.csv) covers 5–30 g, factors 1/3/5/10 and all four apex heights for both string topologies. A taller triangle reduces inward load, though even a nearly vertical continuous loop retains the cross-board segment's tension. A non-sliding knot at each hole changes the topology and is not assumed here.

The [one-corner/misalignment cases](one_corner_misalignment.csv) apply up to twice the balanced local vector to one corner, then rotate it out of plane by 0/15/30/60°. This is a defined fixture screen for unequal handling, not a solved equilibrium of an asymmetric slipping loop. At the 20 mm-apex example, twice the nominal corner vector is 1.825 N; rotating it 30° gives 0.913 N transverse force. A membrane-only calculation cannot assess that transverse case.

## Which mechanical modes the changes address

**Bearing at the line contact.** A thin string is not a close-fitting bolt. Dividing load by `hole diameter × thickness` spreads it over too much material. A useful nominal contact-demand indicator is `R_hole/(line diameter × core thickness)`, recognizing that the true contact width and direction depend on deformation and wrapping. At the example 20 mm apex, a hypothetical 0.2 mm line gives **14.72 MPa** by this indicator. Using the 2.7 mm hole diameter would misleadingly give **1.09 MPa**. No line diameter, modulus or contact-area measurement is available, so neither is a predicted local maximum.

Making the hole smaller does **not** directly reduce that line-based pressure indicator. Plating may spread force around the rim and avoids exposed cut glass at the bore, but its actual benefit needs the formed barrel/rim and line contact. Do not describe the nominal hole diameter as a bearing width for this string.

**Tearing the edge ligament.** The conservative nominal two-plane comparison `τ=R_hole/(2 e t_core)` uses the minimum ligament `e` regardless of direction. It intentionally does not assign an exact crack path in a rounded corner. At the same example, it changes from **1.476 MPa existing**, to **1.092 MPa for 2 mm unplated**, and **1.107 MPa for 2 mm plated** when substrate drilling allowance is included. That is about a **25% reduction in this FR-4 demand indicator**. The plated and unplated comparison separates the geometry benefit from unquantified metal load sharing. It is not a material strength margin or a prediction of which mode initiates failure.

**Global net section.** An average vertical stress across the full board width minus the two substrate holes changes only from about 0.176 to 0.164 MPa in that case. This broad net-section average cannot clear the concentrated corner/string contact. The inward loads also compress the top region between holes; any initial warp or out-of-plane loop geometry can couple that compression into bending.

**Out-of-plane bending.** The [strip screen](out_of_plane_screen.csv) varies a hypothetical 2–8 mm effective width, 2–10 mm unsupported reach, 15–25 GPa elastic modulus and transverse load 0.02–1 N. It uses `σ=6 Fz L/(b t²)` and `δ=Fz L³/(3 E I)`, with `I=b t³/12`. For a 4 mm wide, 5 mm long bare-core strip with E=20 GPa, 1 N transverse load produces a nominal **78 MPa** bending demand and **0.21 mm** tip displacement. Actual load spreading, copper, clamps and plate action differ. Cases with displacement over 10% of span are flagged as outside the selected small-deflection screen. They are not accepted linear predictions of large deformation.

**Copper as a local stiffener.** Perfectly bonded, continuous 35 µm copper on both faces of a bare 0.31 mm core gives an ideal local bending-rigidity ratio of **4.70–7.17×** over hypothetical E=25–15 GPa bare cores. At E=20 GPa the value is **5.63×**, while extensional rigidity rises **2.24×**. Those results show why a rim with copper on both faces can matter despite copper's small mass. They do **not** mean the proposed mounting hole or whole board becomes 5.63 times stronger: a ring is finite, the old board already has copper, adhesion can peel, and copper may yield before the laminate. The [stiffness screen](copper_stiffness_screen.csv) explicitly assumes full-width bonded skins and omits those limits. A larger pad without a barrel would not wrap the bore or connect its two face rings mechanically through plated copper.

**Line abrasion and cutting.** This can govern even when FR-4 stresses are modest. The string turns around the entry/exit rim; a plated wall is not automatically a polished radiused eyelet. Rim burrs, copper nodules, mask edges, the knot, fretting, dirt and repeated stretch affect the line. A smaller bore preserves material but does not increase the through-thickness lip radius. Use clean unsoldered holes and inspect the actual rim; do not fill them with solder to imply a structural improvement. If the actual line shows wear, a tiny smooth sleeve or a different soft bridle can be evaluated and weighed. Neither is selected without the line dimensions and fit.

## Material evidence and elasticity

[Shengyi's S1141 data](https://www.syst.com.cn/en/product/info_122.aspx?itemid=1176) give typical flexural values of 600/500 MPa and 1 oz peel values of 1.8 N/mm after a specified solder exposure and 1.6 N/mm at 125°C. The supplier says typical values are based on **1.6 mm specimens**, with additional thickness qualifications, and are reference values. The delivered Stratolink laminate is not identified as S1141. Those values are context for the material class, **not allowables for this 0.4 mm drilled corner, line bearing, copper peel or cold fatigue**. The calculations assign no material strength and no failure safety factor. The 15–25 GPa FR-4 modulus sweep and 110 GPa copper modulus are explicitly generic stiffness assumptions; the cited S1141 table does not provide those modulus values.

Stretch in the string can reduce peaks for a given absorbed energy if it has enough travel. It does not make a peak load known: slack, rate, cold stiffness, damping and knots matter. The [elastic-slack screen](elastic_slack_screen.csv) uses a deliberately ideal, initially unextended linear spring after a slack fall: `F_peak = mg + sqrt((mg)²+2 k mg h)`. It varies stiffness rather than assigning one to the user's string. This illustrates sensitivity only; it is not a measured shock model of the balloon.

## A useful first-article comparison

Use the actual string, actual triangle height and measured complete payload mass. Compare the existing and selected hole designs under the same setup. Support the board body in a broad fixture, leaving the top corners free; avoid clamping away the hole deformation of interest.

1. Record the finished bore/rim condition, core/finished thickness, line diameter, knot and front/back threading. Photograph both rims and the line under magnification.
2. Load the complete bridle slowly while measuring force and corner motion. Choose a proof multiplier from the intended handling envelope; the 5× model case is a proposed engineering screen, not an already approved rating. Repeat with each corner carrying the specified asymmetric fixture load and with a modest known out-of-plane offset.
3. Inspect after unloading for cracks, pad lift, barrel damage, permanent board bend, knot slip and line cuts. Cycle the actual line over the actual rim while loaded, then inspect and compare retained breaking strength with an uncycled sample of the same line. Recording the cycle count and tension is more useful than claiming generic abrasion resistance.
4. Repeat the relevant load/line observation after exposure to the intended temperature range. Record temperature at the hardware and line rather than substituting ambient-air estimates. A first article can establish a process baseline; it is not a statistical reliability demonstration.

The geometry and relative simulations justify this specific low-mass revision now. The physical checks distinguish a strong laminate rim from a durable suspension assembly.

## Reproduce

```sh
python3 analysis/v1_1_suspension_20261012/mechanics/model.py
```

The script reads the pinned board through Git, reuses the tracked S-expression reader, and writes only this directory. Six checks verify extraction, force balance, the extra bottom-segment tension and ring-mass consistency. It produces [summary.json](summary.json), geometry and load tables. It performs no CAD edits or physical tests; the separate FE study owns its own mesh and convergence evidence.
