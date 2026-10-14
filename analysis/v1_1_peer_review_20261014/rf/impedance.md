# Grounded RF feed model

The board declares a 0.31 mm FR4 core, relative permittivity 4.5 and 35 µm copper. Those are CAD inputs, not measured laminate properties or a supplier impedance commitment.

`cpw_screen.py` uses the [Qucs grounded coplanar equations](https://qucs.sourceforge.net/tech/node86.html), with the first-order copper-thickness correction described in [scikit-rf's CPW implementation](https://scikit-rf.readthedocs.io/en/latest/_modules/skrf/media/cpw.html). SciPy receives elliptic parameter `m=k²`, not modulus `k`. The model assumes infinite same-side ground strips and an uninterrupted opposite-side ground plane.

A **0.45 mm trace with a 0.15 mm coplanar gap** gives approximately **48.5 Ω** with the declared core and first-order 35 µm correction. It is a reasonable starting geometry for the short replacement feed. This is not a field solution of the actual finite board. The original interrupted-reference feed cannot be assigned one uniform impedance from its nominal width.

An illustrative corner sweep gives **41.1–56.4 Ω**, using widths 0.425/0.475 mm, gaps 0.125/0.175 mm, core thicknesses 0.279/0.341 mm, relative permittivities 4.0/4.8 and copper thicknesses 0.025/0.045 mm. These ranges are deliberately stated assumptions, not verified JLC tolerances. The sweep demonstrates sensitivity; it does not establish a production bound.

The calculation omits solder-mask dielectric, loss, roughness, finite ground width, pad/ESD/via discontinuities and antenna loading. The source itself qualifies part of its finite-thickness correction. Obtain the final fabrication stackup and validate assembled matching, GNSS signal quality and converter/radio coexistence before treating the new geometry as qualified. Neither DRC nor this model establishes a flight-performance improvement.

Run `analysis/.venv/bin/python analysis/v1_1_peer_review_20261014/rf/cpw_screen.py`. Results and all assumed inputs are in `cpw-screen.json`; rendered primary-source captures are in `../sources/`.

The final board has finite asymmetric front grounds. Independent sampling finds a minimum 0.300 mm added guard, maximum 0.167 mm gap on that side, and at least 0.635 mm ground on the other side, with a transition gap reaching 0.396 mm. Rear reference is continuous beyond the antenna-pad transition within the 5 µm polygon screen. These actual geometries do not satisfy the ideal infinite-ground model uniformly; 48.5 Ω is a starting estimate, not a qualified final feed impedance. See [reference check](../digital/final-rf-reference.json).
