# Assembly rotations for the engineer reroute

The old Y24 cart and its absolute rotation profile do not apply to this board.
The new exports are for supplier review. JLC sign-in and the new placement
preview remain pending.

| Part | Native side / angle | Draft CPL angle | Evidence and remaining check |
|---|---|---:|---|
| U1 BQ25570 | bottom / 180° | 270° | Same side, 180° rotation from the previously checked placement. Apply the same 180° change to its old supplier angle of 90°. Confirm pin 1 at the upper left in the north-up bottom preview. |
| U2 RAK3172 | top / 180° | 90° | Same pose and part as the previous supplier preview. |
| U3 MAX-M10S | top / 180° | 180° | Same angle and side; new position. Confirm the module pin-1 corner. |
| U4 MS5611 | top / 0° | 270° | Same pose and part. Use the package index, not its pressure port. |
| U5 TMP117 | top / 180° | 180° | Rotated 180° on the same side. Confirm A1 against the numbered ball map. |
| U7 LIS2DH12 | top / 90° | 0° | Same pose and part as the previous supplier preview. |
| U8 TLV8801 | top / 180° | 180° provisional | Changed from bottom to top. This is the native export convention, not a verified supplier angle. New preview is required. Native pin 1 is at (57.710, 50.170) mm; three leads lie on the right in the top view. |

U6 is omitted from this pilot. Its new 180° orientation requires a separate
preview before a future populated AS7331 build. C5, antennas, solar attachments
and programming contacts remain hand-assembled and are excluded from the CPL.

Recheck every populated component on both sides after uploading the new BOM,
CPL and Gerbers. Keep any supplier-angle corrections in the profile and
regenerate the package so repository files match the preview. Do not use browser
rotation changes without recording them in the exported profile.
