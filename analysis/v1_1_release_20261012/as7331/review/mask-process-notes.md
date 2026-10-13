# Mask process evidence — 2026-10-13

The user's latest finish instruction requires **green solder mask and no silkscreen**. This supersedes the earlier bare-board direction; copper artwork remains acceptable.

The live [JLC rigid-PCB capability table](https://jlcpcb.com/capabilities/pcb-capabilities), inspected in the in-app Browser and retained in `jlc-mask-capabilities.txt`, lists:

- Pad-to-mask opening ratio 1:1 after the June 2025 LDI upgrade. Reorders follow previous production files.
- At least 0.09 mm between a mask opening and a neighboring trace.
- Minimum green-mask bridge/pad spacing of 0.10 mm for 1 oz copper; 0.20 mm for 2 oz.
- Mask dielectric constant 3.8 and ink thickness at least 10 µm.

The [basic-design article](https://jlcpcb.com/blog/basic-design-of-solder-mask), updated September 9, 2026, also describes +0.05 mm per-side standard expansion for 1/2-layer manufacturing while discussing 1:1 LDI in its multilayer section. These two primary pages have a scope ambiguity. The direct capability table is the clearer manufacturing statement, but the ordering instructions and reviewed CAM image should explicitly preserve original mask dimensions for fine pitch. A generic +0.05 mm expansion must not be applied silently to the U6 footprint: its 0.15 mm copper gap would leave only 0.05 mm nominal mask web. Zero expansion leaves a 0.15 mm nominal web; +0.025 mm leaves 0.10 mm.

TI TMP117 primary package drawing YBG0006-C01 (SNOSD82D, printed p44; cached at `analysis/v1_1_layout_20261012/pcb_audit/sources/tmp117-package-44.png`) gives six 0.23 mm diameter exposed lands at 0.4 mm pitch. The preferred NSMD detail specifies radial mask-to-pad clearance 0.05 mm **maximum**. Its alternative SMD detail specifies at least 0.05 mm metal overlap beneath the mask. The native 0.23 mm copper lands with 1:1 mask have 0.17 mm nominal inter-opening gap; a +0.025 mm expansion gives 0.12 mm. These scalar pad calculations do not inspect escaping traces or other apertures and therefore do not replace the final native/Gerber screen.

Ordinary tented vias are not the same process as soldermask-filled or epoxy-filled-and-capped vias. Do not imply an order for filled vias merely because a via lacks mask openings. The retained exposed U1 thermal holes and exposed suspension/solar through-hole lands need explicit exceptions to ordinary via tenting.

Mask changes alter the RF feed's dielectric surroundings even if the copper and ground return are unchanged. The GNSS ground comparison can prove preserved conductor geometry; it cannot prove identical RF tuning after adding mask. The earlier bare-board geometry is a regression reference, not a measurement of final antenna match.
