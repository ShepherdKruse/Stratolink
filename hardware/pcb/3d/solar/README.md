# Solar assembly models

The left and right ZachTek-style panel assemblies are attached to **J2 and J1** in the canonical PCB and their reusable footprints. Open the board's **3D Viewer** (`Option+3` on this Mac), zoom out and orbit to see the panels, root solder joints and positive return wires. These are portable project-relative VRML assets, with no additional footprints or BOM items.

Each inner **negative** terminal is inserted into its side notch and joined to the GND copper on both PCB faces. The panel begins bending outside the board. A red insulated **positive** lead returns from the outer terminal to the lower +SOLAR through-hole; its bare copper end passes through the board. The display does not imply that the wire is a qualified structural brace. This polarity differs from the original ZachTek transmitter's assembly illustration.

See the [assembled views and short assembly guide](../../../../analysis/v1_1_solar_attachments_20261012/assembly/README.md).

## What is real and what is illustrative

Notch positions, PCB thickness, GND lands, positive-pad locations and drill diameters come from the current KiCad design. The model seats the exposed negative terminal surface against the upper notch bank and inserts it 1.0 mm, leaving the rounded inner tip unoccupied. Both sides use the same nominal panel shape; the small difference in wire endpoints follows the actual pad coordinates.

The panel's **71 × 40 × 0.20 mm** laminate, **3 mm** terminal strips, **95 mm bend radius**, eight cosmetic cell bands, solder shapes and wire diameters are **illustrative estimates**, not a ZachTek dimensional drawing. The first 3 mm of the panel is straight, including 1 mm inside the notch. Bend radius is a display parameter, not a vendor-approved minimum. Red sleeves are shown at 0.70 mm diameter over 0.40 mm conductors; rendered lead paths are about 73.5 mm long, not wire-cutting instructions. Terminal metal is visually offset 0.028 mm from the laminate, with that metal face seated at the notch bank.

The [captured product page](../../../../analysis/v1_1_solar_attachments_20261012/sources/zachtek-panel.txt) supports nominal 4.8 V and 1.76 g; the SKU/title specifies 50 mA. The [assembly reference](../../../../analysis/v1_1_solar_attachments_20261012/sources/zachtek-assembly.pdf) establishes the crossed-sheet mounting concept and approximately 90 mm reference leads, but does not dimension this model. Actual panel size, strip preparation, solderability and final bend need measuring before treating this as a fit model.

## Regenerate

From the repository root:

```sh
python3 hardware/pcb/3d/solar/generate.py
```

Python's standard library is sufficient. This rewrites only the two `.wrl` assets and `geometry.json`. Reload the 3D viewer after regenerating. The generator does not edit the board or schematic.

Construction coordinates are millimetres relative to each notch: x right, y down the board, z toward the board front, with z=0 at the board midplane. VRML coordinates are divided by 2.54 and y is inverted. The footprint model offset of z=−0.2 mm places that midplane within the 0.4 mm board. Keep the model references in both the PCB and reusable footprints when updating them.

These colored meshes support KiCad's 3D viewer and image renderer. They are not STEP solids, so do not expect the panels to appear in a STEP-only mechanical export. Copper, mask, holes, outline and schematic are independent of these visual assets.
