# Independent assembly-model review

2026-10-12. Read-only review of the promoted 1 × 2 mm notch revision and the photo-scaled models. No CAD or model assets were changed by this review.

The model is internally consistent with the proposed assembly. Both sides of `geometry.json` reproduce exactly when the generator is imported without invoking its writer. The native [front](views/assembled-front.png), [rear](views/assembled-rear.png) and [ground-joint detail](views/ground-joint-detail.png) show the correct opposing panels, retained rear capacitor, central positive contacts and lower PCB lead entries. These images support visual placement, not a full component-solid collision certification.

The generator's local axes and 2.54 mm VRML conversion agree with its project model references. Both PCB and library references use the −0.2 mm Z offset to align the displayed assembly midplane with the 0.4 mm PCB. The notch origins and lower positive holes agree with the model: J2 `(53.3165, 54.5)` to `(54.8, 85)` and J1 `(76.6755, 54.5)` to `(75.2, 85)`.

| Check | Result |
| --- | --- |
| Root fit | 1.5 mm insertion reaches the end of the straight bank of the 2 mm-deep, R0.5 notch. The exposed terminal face seats at local Y = −0.5 mm. |
| Laminate envelope | Assumed 0.20 mm film spans Y = −0.472 to −0.272 mm, leaving 0.772 mm nominal to the opposite bank. This is model geometry; actual prepared thickness remains unmeasured. |
| Straight root | 7 mm covers the nominal 5 mm inner terminal, including the photo's conservative 6.5 mm high estimate. |
| Copper lead versus panel | Conservative full-radius capsule screen finds no intersection: approximately 0.031 mm minimum clearance to an envelope that includes terminal metal. The small minimum occurs near the intended positive solder contact. |
| Hook versus free edge | Approximately 0.793 mm minimum metal-envelope clearance after subtracting the full copper radius. |
| Insulated return versus panel | Approximately 0.894 mm minimum clearance to the same envelope. |
| Positive hole fit | Vertical bare 0.50 mm stem through the 0.70 mm hole: 0.10 mm nominal radial clearance, or 0.06 mm at the recorded 0.62 mm minimum finished hole, before wire/tinning tolerances. |
| Ground fillets | Both face menisci contact the same terminal face and the upper-bank copper. Their X span is 1.2 mm inside the nominal 1.3 mm available overlap. The Y base extends to −1.20 mm, inside the pad's −1.40…−0.72 mm interval. |

Three limits should remain explicit. First, the display fillets now overlap copper by 0.48 mm across the bank, giving 0.576 mm² modeled base contact per face; this mesh is an illustrative meniscus and must not be used as a qualified joint area or strength. The base was enlarged from 0.12 mm after this review so the picture depicts wetting more of the available land, without changing CAD. Second, only the inner negative strip remains straight: the outer positive strip follows the R140 curve through approximately 2.05°. No supplier-approved bend limit has been established. Third, the generator's `wire_hook_clears_outer_edge_mm: 1.0` denotes a 1 mm extension in developed panel station before the turn; it is not a guaranteed 1 mm physical surface clearance. The capsule calculation separately checks actual modeled clearance.

The solder bead at the outer terminal and fillets at the root intentionally meet panel metal. Their contact is excluded from an unintended-collision claim. Real foil thickness, tinning, bend tolerances, wire springback and deflection require the first physical assembly checks described in the [qualification record](README.md). The mathematical clearance calculation does not certify those tolerances or strength.

Reproduce with `analysis/.venv/bin/python analysis/v1_1_solar_attachments_20261012/qualification/review_model.py`. The script imports the generator, reconstructs its meshes in memory and writes only [model-review.json](model-review.json). It records source, metadata and canonical PCB SHA-256 hashes. For wire clearance it compares the full centreline radius against a 0.01 mm-station panel cross-section; the straight-root and curved-film geometry is uniform across the width occupied by the wires. The expanded full-metal envelope is conservative over the active cell region.
