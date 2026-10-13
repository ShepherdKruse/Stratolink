# U2 C5452091 supplier orientation review

2026-10-13. **PASS for the explicitly reimported C5452091 / RAK3172-8-SM-NI model at CPL rotation 90°, top side, center (64.950000, −72.205000) mm.** Retain the board's component placement and center; apply this as a supplier-part-specific CPL correction. The initial C5452091 rendering at CPL 180° is incorrect. This review made no CAD or supplier edits.

The decision uses actual numbered copper lands and the asymmetric module pin pattern, not the direction of the rendered U2 text. [Native U2 extraction](native-u2.json) records pad 1 at PCB (59.215, 79.605) mm, below and left of the component center in a north-up top view. The [RAK3172 manufacturer pin layout and pin table](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/) identify pin 1 as UART2_RX/PA3 and pin 12 as RF. On this board:

| Module edge in north-up top view | Required numbered pads |
|---|---|
| Bottom | 1 through 12, left to right; RF pad 12 at lower-right |
| Right | 13 through 16, bottom to top |
| Top | 17–19 on the right, gap, 20–24 on the left |
| Left | 25 through 32, top to bottom |

The [initial CPL180 screenshot](../sourcing_followup/u2-placement-initial-crop.png) places the supplier's pin-1 marker at lower-right and the 12-pad edge on the right. It is rotated 90° counterclockwise from the needed orientation. Numeric rotation conventions are not assumed from that image: the parent explicitly reimported a probe CSV changing U2 to 90°, and the resulting [zoomed screenshot](../sourcing_followup/u2-placement-cpl90-full.png) and [full-page screenshot](../sourcing_followup/u2-placement-cpl90-page.png) were independently viewed.

The CPL90 result has the purple supplier pin-1 marker at the lower-left and the 12 castellations aligned along the lower edge. The four-pad right edge, split top groups and eight-pad left edge also agree. The asymmetric shield/PCB outline and copper overlay agree without a center translation. The selected row visibly identifies **U2, C5452091**, so this is a review of the new supplier part rather than the old C18548052 model. The [captured DOM](../sourcing_followup/u2-placement-cpl90-dom.txt) independently records the 90° value.

The exact uploaded [probe CSV](../sourcing_followup/CPL-U2-90-probe.csv) hashes to `2b30ba3a50a094b84f2d44d6a20fd72512fbb8cef4a92adf45084ac3c8f31efa` and contains:

```csv
U2,64.950000,-72.205000,top,90.000000
```

The paired candidate BOM at `scratch/stratolink-release-20261012/sourcing-followup/r4-u2-exports/BOM-stratolink.csv` hashes to `1ac1cad1786e2d40b2a6d10cb758c353929e9faeed5aa1db922c60bcbad958f1`; its U2 row is RAK3172-8-SM-NI / C5452091. The generated candidate CPL in that same scratch export directory still had the earlier 180° at review time and is **not** the uploaded 90° probe. The supplier profile and regenerated release export must carry the reviewed 90° before final upload.

Image hashes: zoomed `583f5396e9d0b53797e54ad10e017dffb42b142479a2a5785e5835d8aa3e7fec`; full page `c215fc7f9a3e1239ab7fb2c985799292fd1a9404bb5783b85e95057b3a765f59`. Additional evidence hashes and the scoped conclusion are in [u2-supplier-orientation-review.json](u2-supplier-orientation-review.json).

This establishes the vendor preview's orientation and centering convention for the named part and probe. It does not establish every delivered unit's solder quality, supplier model dimensional tolerances, or radio performance. The native footprint's KiCad rotation remains 180°; changing that would wrongly rotate the physical board geometry. The correction belongs to the exact supplier CPL profile.
