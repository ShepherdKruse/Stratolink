# v1.1 fabrication intent — working revision

This describes the current CAD intent, not a released manufacturing package. Use [TODO.md](TODO.md) to close the remaining part, rule, stencil and pilot checks before ordering.

**NO SOLDER MASK — BOTH SIDES. NO VIA TENTING.** This is Teddy's explicit preference for the payload board. The two full-board openings on F.Mask/B.Mask are deliberate and must be interpreted as removing all coating from both faces, including ground copper. Confirm that the fabrication settings and CAM interpretation agree. Do not substitute empty mask artwork or add local mask dams during cleanup.

The selected nominal stackup is two layers, **0.40 mm total**, with **0.035 mm copper on each face** and a **0.33 mm FR4 core**. Mask thickness is zero. These are CAD values; confirm the available construction with the fabricator. Copper surface finish remains a separate choice and is not specified by the absence of solder mask.

Preserve front/back stencil-paste data for assembly. Solder mask and stencil paste are different layers; omitting mask does not mean flooding the board with solder paste. U7's existing aperture-area review remains on the checklist.

The existing `GND` and `+` legends are retained. None overlaps a solder pad, although portions now lie over exposed copper. Confirm which bare-board legend the fabricator can retain. The copper artwork and its clearances must remain unchanged.

AE1/AE2 are **hand-formed enameled copper wire**, not the inherited Adafruit/Johanson parts. The [published antenna instructions](https://stratolink.org/docs/hardware#antennas-and-suspension) give starting lengths from the feed: 82 mm for 915 MHz LoRa, 86 mm for 868 MHz, 83 mm compromise, and 48 mm for GNSS L1. Strip enamel at each solder joint. The CAD reference uses 82/48 mm; record the selected regional length and actual wire diameter for the pilot and check the completed assembly's match.

The project ignores only the **mask-bridge** check made inapplicable by this finish; raw enabled findings are retained in the [review evidence](../../analysis/v1_1_bare_finish_20261012/README.md). Other inherited fabrication/identity findings still need their own dispositions. No order or upload has been performed.
