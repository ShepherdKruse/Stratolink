# Fresh 2.0 mm notch exports

[Review exports](review-exports.zip) contain 17 fresh Gerber, Excellon and SVG files from the checked upper-bank revision. [Manifest](archive-manifest.json) pins the input hashes and every export. [Native export checks](evidence.json) passed without modifying the candidate.

- Edge.Cuts exports identify a **non-plated profile**. Both open notches are **1.0 × 2.0 mm**, with exact R0.5 tip arcs.
- One 0.7 mm plated positive hole and one 0.3 mm ground stitching via per side match the PTH export.
- Total drill counts: **165 PTH / 3 NPTH**. No Excellon slot commands, no drill in either open notch, and no J1/J2 paste apertures.
- Upper-bank GND lands are on both copper/mask faces. The notch wall is unplated; solder bridges to the exposed panel terminal, not to wall plating.
- No new mounting courtyard conflicts or unconnected copper.

These exports document fabrication geometry; inherited DRC/ERC findings and physical joint qualification remain separate.
