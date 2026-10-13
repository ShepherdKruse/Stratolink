# JLC matched-parts selection review

**PASS — 2026-10-13.** The saved `matched-parts-selection.txt` contains exactly 57 unique part rows, all checked. Each row's matched manufacturer part number and LCSC number equals the pilot BOM; uploaded comments and footprints also match. The reference set and top/bottom columns equal the CPL.

- C14 and C23: CL05B104KO5NNNC / C1525, selected.
- R27: MCU0805MD3304BP500 / C4313228, selected.
- U6 is the sole omitted part from the 58-part design assembly set, matching the explicit pilot population profile.
- No discrepancies found.

`parts-selection-review.json` contains every row and source hashes. Reproduce with `python3 review_parts_selection.py`. This audit uses only the saved snapshot and local package; it does not inspect subsequent browser changes or verify coordinates/rotation, which are absent from the BOM page.
