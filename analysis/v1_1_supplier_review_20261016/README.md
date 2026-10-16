# JLC pilot draft, 16 October 2026

Saved **fabrication-review_Y25** in the [JLC cart](https://cart.jlcpcb.com/shopcart/cart). PCB `Y25-2680969A`; assembly `SMT026101663307-2680969A`. The stale Y24 draft was removed after checking Y25. No checkout or payment was submitted.

The quote is **$332.63**: $70.63 fabrication and $262.00 assembly. Shipping, tax and charges for advanced options after manual review are excluded. This is a saved review draft, not factory CAM acceptance.

## Files and population

- Native PCB remains `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`. No CAD or routing changes were made in this supplier pass.
- Current [manufacturing package](../../hardware/gerbers/v1.1-pilot-supplier-20261016/README.md) contains the corrected CPL. U8 changed from 180 to 90 degrees in the supplier coordinate convention. Its center, side and all 56 other placement rows are unchanged.
- The actual uploads were the original frozen `hardware/gerbers/v1.1-pilot/fabrication-review.zip` and BOM, followed by the corrected CPL from the new package. The regenerated Gerbers and drill files differ only in export timestamps. Both packages have identical BOMs, native positions and stencil PCB bytes.
- JLC's matching page was checked against the files: **57 references, 41 top and 16 bottom**, with exact MPN, LCSC, footprint and side matches. All 57 were explicitly selected after each import. JLC initially left several matched parts deselected; that was corrected before saving.
- **U6 AS7331 is omitted. C14, C23 and R27 are fitted.** Only U6's 16 paste apertures are removed. C5, antennas, panels and mounting hardware are hand-fitted.

## Saved construction

Five fabricated boards and three assemblies; Standard PCBA on both sides. Two layers, 0.40 mm FR4, green solder mask, ENIG 1 microinch, 1 oz copper, tented vias and no silkscreen. JLC's generic silkscreen color field reads White; both supplied legend layers are empty and the saved remark explicitly requires NO SILK. The supplier rail envelope is 71.36 by 71.30 mm; the board itself is 57.30 by 23.36 mm.

Production-file and part-placement confirmations are enabled. Both were configured without automatic confirmation. Saved remarks require manual approval, unplated solar notches, preserved mask/tenting, appropriate stencil review and rails clear of solar banks and suspension holes. See [PCB details](cart-pcb-details.txt) and [assembly details](cart-assembly-details.txt).

## Placement results and remaining review

The [independent placement review](final-placement-review.md) checks all seven populated ICs against the native pad map. U8's fresh corrected import shows three leads right, two left and pin 1 lower-right. U1, U2, U3, U4, U5 and U7 agree with their required indices. The generation profile retains its original provisional wording as provenance; the subsequent screenshots and this review establish the observed result.

D1, D3 and L2 use checkerboard placeholders in JLC's preview. Their real body orientation and clearance still need factory review. D1/D3 are bidirectional TVS parts. The saved cart's grouped BOM display repeats some designator labels, while the matching page and submitted CPL contain 57 unique references and the cart lists 30 selected part groups with no unselected parts. Confirm 57 placements in the factory production files. The cart also displays untranslated product-description text; the quote page selection was Development Board.

Factory review must still accept the fine-pitch lands, mask details, copper microdetail, stencil and rail positions. The engineering review's RF, cold, power and mechanical bench checks remain open. No production approval is implied by the cart or this placement review.

## Verification

```sh
python3 analysis/v1_1_supplier_review_20261016/verify.py
```

This checks the recorded file hashes, final BOM selection and the single U8 CPL change. The earlier engineering evidence and downloadable KiCad sources are preserved unchanged. `package-comparison.json` separately records the full source, fabrication and stencil comparison. Screenshots show the browser preview, not manufactured hardware.
