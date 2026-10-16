# Final mechanical and manufacturing sweep

Reviewed the live PCB with SHA-256 **e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13** against frozen review commit `a146a174d5bbb49c61890e4a17ce455ca31b1f70` and the Y25 supplier package. No additional mechanical CAD change is indicated by this sweep. The root review restored the missing VSTOR segment and strict project settings before these final checks.

[Source comparison](source-comparison.json) finds only five hidden F.Fab value fields, on C22/R24/R25/R26/U8, relative to the frozen PCB. Every other board expression, including routes, vias, zones and their saved fill, footprint geometry, models, outline and stackup, is identical. All project library/model assets match the frozen files; generated Python caches are excluded. Fresh mask, silk and outline Gerbers match Y25 exactly after removing only their creation timestamps. [Artwork comparison](Y25-artwork-comparison.json). The project again treats mask bridges as errors and requires 0.09 mm mask-to-foreign-copper clearance. Schematic electrical parity and fresh zone connectivity are covered by the separate final electrical review.

The board remains a valid single closed outline, **23.364 × 57.305 mm**, area **1329.560 mm²**, nominal **0.40 mm** finished FR4. Its modeled stackup is 0.035 mm copper per face, 0.31 mm core and 0.01 mm green mask per face, with ENIG. Both native silk layers have no artwork and both exported silk files contain zero draw/flash commands. Ordinary vias remain tented. Copper polarity marks and exposed solar connection lands remain intact. [Geometry measurements](geometry-review.json).

| Feature | Fresh result |
|---|---|
| Ordinary routed copper to edge | Minimum 0.2010 mm; no routed copper outside outline |
| Ordinary component annular ring | Minimum approximately 0.190 mm |
| Ordinary via annular ring | Minimum 0.150 mm |
| U1 thermal-hole annular ring | Intentional approximately 0.100 mm, not the ordinary-hole rule |
| H1/H2 suspension | 2.00 mm plated holes, 3.20 mm solid GND rings |
| J1/J2 solar attachment | Existing 1.0 × 2.0 mm open unplated notches; solid GND banks on both faces |
| Solar positives | 0.70 mm PTH holes, 1.40 mm lands |
| J3/J4 programming | 0.50 mm holes, 0.88 mm front lands, enlarged rear lands retained |

Ground zones and pad connection overrides match the reviewed reroute. Solar GND banks and suspension rings explicitly use solid zone connections. The stored thermal parameters do not imply those solid pads have relief spokes. The final electrical review checks refill, opens and the enabled named exceptions; this mechanical sweep does not reinterpret the 0.05 mm small-zone settings as the board's general manufacturing clearance.

Fresh plotted-mask checks expose all thirty repaired U1/U4/L2 lands fully. Minimum aperture-to-foreign-copper gaps are **0.1100 / 0.1005 / 0.1000 mm**, respectively; minimum mask webs are **0.1800 / 0.5966 / 0.5200 mm**. These pass the scoped 0.09 mm gap and 0.10 mm web checks. [Mask evidence](plotted-mask-review.json). The scoped check does not replace the board's fine-pitch exceptions or factory mask registration review.

All **68 footprint instances** load from the project library and their normalized pad geometry and local settings match. All **63 model attachments** resolve with the KiCad 10 standard model library installed; normalized model lists/transforms match their local footprints. J3/J4/J20/H1/H2 intentionally have no purchased-part model. [Pad comparison](library-pad-comparison.json), [model comparison](model-transform-comparison.json), [source/model hashes](models-pads.json).

Native mesh export confirms the **48 mm GNSS wire points up** and the **82 mm LoRa wire points down**. The modeled GNSS wire clears the solar assembly by **20.54 mm** and its terminal metal by **21.21 mm**. Its small 0.0105 mm board-surface display intersection is retained from the prior model; it is not a measured wire standoff. The actual triangular bridle must stay behind and clear of the GNSS wire throughout motion. XY string crossings alone do not establish a physical collision.

C5's maximum case rectangle retains **2.306 mm** clearance to the outline and **0.696 mm** to AE1's rear copper land, with no projected overlap of other rear lands. No rear component has moved into the case envelope. Allow for real solder fillets, insulation and placement before hand fitting C5. Solar film thickness, bend and terminal solder shapes remain nominal display assumptions. [Assembly measurements and limits](assembly-review.json), [native wire mesh](antenna-model-mesh-review.json).

Fresh renders were visually inspected: [full assembly](visual/assembly.png), [front](visual/top.png), [rear](visual/bottom.png). They show the full design, including U6; the existing Y25 pilot assembly omits U6. Hiding the five F.Fab values changes those fabrication labels, with no effect on copper, mask, paste, drills or these 3D views. [Render arguments and hashes](render-review.json).

Factory questions remain bounded to actual process acceptance: confirm 0.40 mm finished construction and panel support/rail/tab positions that leave the notches and holes usable; preserve supplied mask openings, tenting and fine-pitch dams; confirm the intended pilot stencil and double-sided assembly process. Y25 placement screenshots are supplier-import evidence, not factory CAM acceptance. The manual assembly checks are the real C5 solder/insulation gap, solar-joint fit and bridle rim wear/security. This review does not claim load, temperature or RF qualification.

Reproduce using the read-only native and geometric scripts in [the earlier mechanical review](../../v1_1_engineer_review_20261015/mechanics/README.md), directed to this directory and the current PCB. Run `review_geometry.py --repo REPOSITORY --frozen FROZEN_REVIEW_WORKTREE --mask SCRATCH_MASK_DIRECTORY` after the native extracts and Gerber exports. [manifest.json](manifest.json) records input and artifact hashes; no CAD source was modified by this sweep.
