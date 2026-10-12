# Solar assembly models

The left and right ZachTek SKU 1044 panel assemblies are attached to **J2 and J1** in the canonical PCB and their reusable footprints. Open the board's **3D Viewer** (`Option+3` on this Mac), zoom out and orbit to see the panels, root solder joints and positive return wires. These are portable project-relative VRML assets, with no additional footprints or BOM items.

Each inner **negative** terminal is inserted into its side notch and joined to the GND copper on both PCB faces. The panel begins bending outside the board. A central **0.5 mm solid copper positive lead** follows the outer terminal face around its free edge, then returns in a straight section to the lower +SOLAR through-hole. A short formed tail passes through the board. The red sleeve shows insulation. The wire geometry is intended to share mechanical load, but its formed ends and the film joint still require physical qualification. This polarity differs from the original ZachTek transmitter's assembly illustration.

See the [current dimension, mounting and assembly record](../../../../analysis/v1_1_solar_attachments_20261012/qualification/README.md). The earlier [illustrative assembly record](../../../../analysis/v1_1_solar_attachments_20261012/assembly/README.md) is retained as history.

## What is real and what is illustrative

Notch positions, PCB thickness, GND lands, positive-pad locations and drill diameters come from the current KiCad design. The model seats the exposed negative terminal surface against the upper notch bank and inserts it 1.5 mm, leaving the rounded inner tip unoccupied. Both sides use the same nominal panel shape; the small difference in wire endpoints follows the actual pad coordinates.

The panel's **94 × 75 mm** developed envelope and nominal **5 mm** terminal strips now come from a calibrated metric grid in [ZachTek's product photograph](https://www.zachtek.com/product-page/copy-of-solar-cell-for-pico-balloons-polymer-4-8v-50ma). The [measurement record](../../../../analysis/v1_1_solar_attachments_20261012/qualification/metrology/README.md) carries conservative photo uncertainty of ±2 mm in length and ±1.5 mm in width. These are image estimates, not supplier manufacturing tolerances. The visible terminal band spans approximately 4–6.5 mm depending on edge/glare interpretation.

The **0.20 mm laminate thickness**, solder menisci and **140 mm bend radius** remain assembly/display assumptions. Thickness and prepared solderable area cannot be recovered from the overhead photo. The first **7 mm** stays straight, including **1.5 mm insertion** into the 2 mm notch; curvature therefore starts beyond the photographed terminal strip. The four groups of five visible fingers imitate the image, not its internal circuit. Terminal polarity must be checked on the delivered panel.

The 0.50 mm conductors fit the existing 0.70 mm holes with nominal 0.12 mm diametral clearance at the recorded minimum finished-hole size, before wire tolerance or tinning. Their central placement avoids the earlier off-center twist. A formed hook clears the panel's free edge before the straight return runs underneath it; do not fold the wire tightly around the film as a structural saddle. The rendered total lead centerlines are about **95.8 mm**, with approximately **87.6 mm** straight return sections. Fit the actual assembly before cutting: model lengths omit process allowances. Red sleeves are 0.70 mm outside diameter. The two modeled copper centerlines weigh about **0.337 g** at an assumed 8.96 g/cm³, excluding sleeve and solder.

The [mechanical screen](../../../../analysis/v1_1_solar_attachments_20261012/qualification/mechanics/README.md) evaluates root moment, compressive wire demand, diameter sensitivity and thermal bow. It does not assign an unmeasured peel strength or turn ideal column behavior into an assembly rating. The [captured product page](../../../../analysis/v1_1_solar_attachments_20261012/sources/zachtek-panel.txt) supports nominal 4.8 V and 1.76 g per panel; the SKU/title specifies 50 mA.

## Regenerate

From the repository root:

```sh
python3 hardware/pcb/3d/solar/generate.py
```

Python's standard library is sufficient. This rewrites only the two `.wrl` assets and `geometry.json`. Reload the 3D viewer after regenerating. The generator does not edit the board or schematic.

Construction coordinates are millimetres relative to each notch: x right, y down the board, z toward the board front, with z=0 at the board midplane. VRML coordinates are divided by 2.54 and y is inverted. The footprint model offset of z=−0.2 mm places that midplane within the 0.4 mm board. Keep the model references in both the PCB and reusable footprints when updating them.

These colored meshes support KiCad's 3D viewer and image renderer. They are not STEP solids, so do not expect the panels to appear in a STEP-only mechanical export. Copper, mask, holes, outline and schematic are independent of these visual assets.
