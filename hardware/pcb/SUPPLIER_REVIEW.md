# Current v1.1 supplier draft

The current JLC draft is **fabrication-review_Y26**, PCB **Y26-2680969A**, assembly **SMT026101664930-2680969A**: five boards, three assemblies. It has been reviewed again on 16 October. Saving the reviewed Y25 item advanced its identifiers to Y26; the files and selected parts are unchanged. Nothing has been ordered.

- [Final electrical, mechanical, population and supplier sweep](../../analysis/v1_1_final_sweep_20261016/README.md)
- [Current UV-omitted Gerbers, BOM and verified CPL](../gerbers/v1.1-final-20261016/README.md)
- [Conditional populated-UV files](../gerbers/v1.1-final-uv-20261016/README.md)
- [Independent IC orientation review](../../analysis/v1_1_supplier_review_20261016/final-placement-review.md)
- [JLC cart](https://cart.jlcpcb.com/shopcart/cart)

Current PCB hash: `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13`. The final sweep restored a deleted voltage-sense trace and strict mask checks while preserving schematic and fabrication-field cosmetics. Current fabrication geometry matches the previously uploaded Y25 files; regenerated BOM/CPL retain the verified U8 supplier rotation of 90 degrees. Historical supplier evidence remains frozen at its original source identity.

U6 is omitted in the saved cart; C14/C23/R27 remain fitted. A sourcing inquiry has been sent to JLC about adding AS7331, emphasizing earliest delivery and total added cost. The populated-UV export is conditional: confirm the exact sourced identity, U6 supplier pin-1 preview, stencil and optical-package handling before use. It is not uploaded to the current cart.

Manual production-file and placement confirmation remain enabled. Factory CAM and final user approval remain pending. The grouped cart summary repeats some designators; the individual BOM review contains 57 unique selected references. Confirm that same unique population in the factory production files.
