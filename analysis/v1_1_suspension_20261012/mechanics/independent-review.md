# Independent review of the membrane FE screen

2026-10-12. Reviewed `../fem/model.py`, frozen input, 18 result rows and nine paired comparisons, including the added narrower contact cases. No FE code was edited by this reviewer.

**The implementation supports a modest comparative membrane-compliance claim under its stated assumptions. It does not establish a stronger hole, greater tear-out capacity, a copper reinforcement factor, or resistance to string wear.** No blocking CST assembly or force-balance error was found. The principal qualifications below should accompany any result shown to the user.

## Checks

- The CST displacement ordering, signed shape-function gradients, positive element areas, plane-stress constitutive matrix and `t A BᵀDB` assembly are consistent. The affine displacement check correctly recovers constant strain and engineering shear.
- The two corner loads include the continuous triangle's bottom-segment tension. Finite radial nodal forces sum to the intended resultant at each bore. The solver checks free-node residual, overall force balance, overall moment balance and `strain energy = external work / 2`.
- The native input hash matches the baseline CAD. The outer top contour and circular cutouts are represented, along with fully contained native pad/via holes. Whole-triangle domain containment prevents triangles spanning the holes. Mesh-area errors are negligible in these runs.
- The principal compliance ratios converge from **0.93018 → 0.92850 → 0.92799** as nominal spacing decreases 0.22 → 0.15 → 0.10 mm. The final ratio changes about **0.055%**; absolute compliance changes about 0.4%. This is useful numerical consistency evidence for that comparison, not validation of the line-contact assumptions.
- Lower-cut sensitivity at y40/42/46 mm gives selected/current compliance ratios around **0.921–0.936**. The assumed support therefore changes magnitude without reversing this comparison. Changing the triangle height has a larger effect: ratios range **0.974 at 10 mm apex** to **0.886 at 80 mm**.

## Contact and interpretation

The initial ±60° pressure arc is a chosen distributed contact, much broader than an unmeasured thin line may actually provide. It also has different physical lengths for the two hole diameters. The additional **±20° case gives compliance ratio 0.961**; a **constant 0.6 mm total arc gives 0.915**. These sensitivities are worthwhile: they preserve the direction of this compliance comparison but show that a precise universal percentage would be unjustified. The narrower cases have denser bore nodes, although only the broad-contact family has a full mesh-spacing sweep.

The field called compliance is **generalized compliance** under a fixed load pattern normalized to 1 N total vertical load. It includes work from the inward forces. It is not simply vertical sag at a hole. Peak displacement is recorded separately.

The 0.2–0.8 mm-from-bore band average is not a failure metric. The bands occupy different physical areas, approximately 13.95 versus 11.44 mm² in the fine broad-contact case. Selected/current band stress is **1.009** there, and **1.08–1.09** in the narrower-contact cases. Accordingly, the model does **not** show reduced local stress overall. The plotted von Mises scalar is a visualization of an isotropic membrane calculation, not an FR-4 failure criterion. The color scale is clipped and must not imply that stresses are capped at its maximum.

## Remaining geometry/material qualifications

The selected main substrate radius is 1.018 mm: a 2.0 mm finished bore plus 18 µm assumed radial barrel thickness. Copper is then omitted mechanically, isolating the substrate geometry. That thickness is a supplier **average**, not a known plating thickness for these boards. Other pad/via diameters in the native input remain their nominal finished CAD values, without individual barrel-drill compensation. The inconsistency is small and shared across variants, but “every actual substrate drill dimension” would overstate the input.

Holes that intersect the artificial lower cut are omitted rather than clipped. Examples are the two 0.3 mm vias centered at y39.946/39.900 for the y40 cut, the via at y42.107097 for y42, and the via at y45.941 for y46. These lie at the assumed support, far from the studied suspension rim. The support-position sweep partly addresses their influence, but documentation should say **fully contained holes are retained**, not all intersecting holes. Clipping them is a possible later refinement if absolute support compliance becomes important.

The homogeneous core thickness, E=20 GPa and Poisson ratio 0.17 are modeling assumptions; the delivered laminate, anisotropy, copper, cold response and adhesive interfaces are not represented. Out-of-plane bending, contact/rope deformation, friction, line cutting, cracks and failure are outside this model. The companion analytical report covers those limitations and suitable first-article observations.

## Mass wording audit

The companion model uses nominal CAD core thickness, generic FR-4 density and 18 µm-average barrel plating. Its **9.87 mg core/full-ring/barrel subtotal is not a whole-board mass upper bound**: ground refill can add copper outside the 3.2 mm pad perimeter, while pre-existing copper reduces added copper within it. The model field and README were corrected accordingly. Full before/after copper unions and measured delivered thickness are needed for a stronger total-mass claim.
