# Nominal added bare-board mass

**The two suspension changes add approximately 13.1 mg (0.0131 g).** This compares baseline `a9d6ed5` against the checked PTH candidate `82926d9d…`, including the actual changed ground fill outside the new pad outlines. No components or routes moved.

| Contribution | Candidate minus baseline |
| --- | ---: |
| FR4, after allowing for pre-plating drill oversize | +2.899 mg |
| Complete planar copper union, both faces | +9.596 mg |
| Copper barrel through the core | +0.705 mg |
| Actual solder-mask coverage change | −0.128 mg |
| **Total** | **+13.073 mg** |

Ground refill adds **3.449 mg of copper outside the two 3.2 mm pad discs**. A calculation using only hole reduction, ring annuli and barrels therefore misses a material share of the change. This estimate uses native KiCad unioned copper, all finished drill openings and actual mask-opening polygons; it does not use a fixed copper or mask coverage ratio.

The CAD stackup contributes 0.31 mm core, 0.035 mm copper per face and 0.010 mm mask per face. Assumed densities are FR4 1.9, copper 8.96 and mask 1.4 g/cm³. Barrel thickness is assumed 20 µm radially. The FR4 calculation expands each plated finished hole by that thickness, then adds the barrel copper across the core; face copper already includes the corresponding annulus, so it is not counted twice. Original circular routed holes are reconstructed at high resolution to avoid the coarse outline polygon's small area bias.

Sweeping only FR4 density from 1.8 to 2.0 g/cm³ and barrel thickness from 15 to 25 µm produces **12.78–13.36 mg**. That range excludes actual copper/core/mask thickness tolerances and surface finish. It is a nominal design estimate, not measured mass or a worst-case upper bound. Solder, ink, finish, string and components are not assigned extra mass here. Using these same assumptions, nominal bare-board mass changes from 1.2483 to 1.2613 g; the delta is more useful than either absolute estimate.

[Full numerical result](mass-delta.json) · [native geometry extractor](extract_mass.py) · [mass calculation](mass_delta.py). The unique scratch source directory is `/Users/twarn/Repositories/ai-working/scratch/stratolink-suspension-mass/`; neither extraction nor calculation modifies CAD.
