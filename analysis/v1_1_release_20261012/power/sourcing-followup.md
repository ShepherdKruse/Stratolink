# R4 and LTR-390 sourcing screen — 2026-10-13

Read-only follow-up after JLC's actual BOM-match page showed R4 C2766827 and U6 C492374 unavailable. No CAD/BOM substitution or purchase was made. The in-app browser was unavailable to this subagent (documented `iab` selection failed; browser discovery returned no backends). The parent explicitly authorized public web research as a fallback. Supplier stock is a retrieved-page observation, not a reservation or proof that JLC can place the part.

## R4: one useful same-value alternative

**Vishay CRCW04023M65FKED** is the best verified shortlist item: 3.65 MΩ, ±1%, ±100 ppm/K, 0402, −55…155°C. The manufacturer's current D/CRCW e3 document 20035, revision 14-Apr-2026, confirms this value range and decodes `F` as 1% and `K` as 100 ppm/K. Standard operation is 0.063 W / 50 V; the larger 0.10 W / 75 V numbers belong to its extended operation limits. The lower standard limits are already ample for R4's divider duty. [Vishay datasheet, pp.1–3](https://www.vishay.com/docs/20035/dcrcwe3.pdf)

DigiKey's opened product page reports **70,639 available**, with cut tape starting at one piece: $0.10 at one, $0.032 each at ten, and $0.0236 each at twenty-five. Part identifier **541-3.65MLCT-ND**. It lists a 1.00 × 0.50 mm body and 0.40 mm maximum height, compatible with the existing 0402 footprint screen. This is a candidate for JLC supplier matching or consignment; JLC acceptance, spare quantity, delivery and any added fees remain to be confirmed. [DigiKey product page](https://www.digikey.com/en/products/detail/vishay-dale/CRCW04023M65FKED/1178412)

Two additional exact-value candidates meet the distributor-listed 0402/1%/100 ppm specification but do not solve immediate availability:

| Part | Retrieved availability | Disposition |
|---|---|---|
| Yageo RC0402FR-073M65L | DigiKey not stocked; listed order quantity is impractical | Secondary sourcing candidate only. [DigiKey](https://www.digikey.com/es/products/detail/yageo/RC0402FR-073M65L/5917664) |
| Samsung RC1005F3654CS, LCSC C4192560 | Out of stock | Secondary sourcing candidate only. [LCSC](https://www.lcsc.com/product-detail/C4192560.html) |

The existing UNI-ROYAL 0402WGF3654TCE / C2766827 remains an electrical match; the live JLC BOM screen is the authority for its zero-stock / 10,000-piece preorder state. No threshold recalculation or route change is needed for a verified same-value, same-or-better-tolerance/TCR substitute. Supplier/manufacturer fields must be changed consistently if a substitute is actually selected.

## U6: exact LTR-390UV-01 remains unresolved

The correct bare sensor remains **LITEON LTR-390UV-01**, LCSC **C492374**; its public product page confirms the exact identifier, I²C interface, 2 × 2 mm package and 1.7–3.6 V supply. The retrieved current page does not expose reliable stock. The parent's signed-in JLC BOM screen reports zero stock and a consignment route. Older indexed LCSC inventory pages show large counts, and a `fat.lcsc.com` category shows 100; neither is evidence that current JLC inventory is available. [Current LCSC product page](https://www.lcsc.com/product-detail/C492374.html)

No currently available bare-part stock at an authorized distributor was verified in this bounded check. DigiKey's previously captured local page says discontinued at DigiKey, and the current indexed product result reports zero. Mouser returned no usable current availability, Arrow's exact product URL returned 404, and an HQonline exact-part page could not be fetched. These outcomes do **not** establish manufacturer end-of-life. [DigiKey exact part](https://www.digikey.com/en/products/detail/liteon/LTR-390UV-01/7322497)

LITEON still hosts the exact sensor datasheet, revision C effective 14-Sep-2024. That is the appropriate primary identity reference, not evidence of shipping inventory. [LITEON LTR-390UV-01 datasheet](https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/LTR-390UV-01_Final_%20DS_V1.7.PDF)

Practical next step: resolve exact-part preorder or consignment with JLC before releasing assembly. Breakout-board availability, unverified broker counts, and similar LTR ambient-light parts do not establish a drop-in source for this footprint and firmware. The current hardware candidate remains unchanged.
