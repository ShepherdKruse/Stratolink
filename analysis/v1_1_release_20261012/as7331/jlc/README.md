# AS7331 pilot — saved JLC cart draft

Canonical CAD is promoted and locally verified. The matching green-mask/no-silkscreen package from `hardware/gerbers/v1.1-pilot` was uploaded, matched, visually reviewed on both sides, and saved to the [JLC cart](https://cart.jlcpcb.com/shopcart/cart) on 2026-10-13. No checkout or payment was performed.

- Cart item: **fabrication-review_Y24**, PCB **Y24-2680969A**, Standard PCBA **SMT026101364685-2680969A**.
- Five PCBs, three assembled on both sides; **57 fitted references / 30 distinct part numbers**. U6 alone is omitted from the 58-reference SMT design; C14/C23/R27 are fitted. Hand-fitted C5, antennas and solar hardware remain outside SMT population.
- **Green solder mask**, 0.4 mm FR-4 TG135, 2 layers, 1 oz copper, ENIG 1 µinch, tented vias, remove JLC board mark, no edge plating or castellations. Actual board is 23.36 × 57.30 mm; JLC adds a 71.36 × 71.30 mm carrier for assembly, subject to CAM review.
- No silkscreen artwork is present. JLC's fixed `White` silkscreen selector is a color default, not artwork; the saved PCB remark explicitly says **NO SILKSCREEN** and the supplied silk Gerbers are empty.
- Quote: **$332.47 = $70.63 PCB + $261.84 PCBA**, before shipping, tax and any assembly-remark review adjustments. Quoted PCB lead time is 3 days; assembly 3–4 days. These are draft estimates, not a placed order.
- Production-file and parts-placement confirmation are enabled. Automatic confirmation was disabled in the quote UI. Factory CAM, stencil-process, carrier/tab and final placement approval remain pending.

Uploaded ZIP SHA-256: `6fd6f81550d8a30e163028bc88d30aad88fad6c8391e8dbdbe215322d3bef4e0`; PCB SHA-256: `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`.

`parts-selection-review.md` and its reproducible JSON audit prove all 57 supplier rows were selected and matched the exact BOM MPN/LCSC and CPL sides. `placement-top.txt` / `placement-bottom.txt` and the placement screenshots record the current import. The top and bottom models were checked against the approved supplier rotation profile: U1 lower-right index, U2 lower-left index and 12-pad lower edge, U3 lower-right index, U4 upper-left separate index, U5 upper-left index, U7 lower-left index, U8 lower-right index with three leads on the right. New/relocated C14, C23, R27 and C21 land/body alignment was visually reviewed. No supplier placement edits were made; the uploaded corrected CPL remains authoritative. A preview is not factory approval or a physical solder-joint check.

`cart-saved.txt` / `.png` prove the new cart item and quantities. `cart-pcb-details.txt` and `cart-pcba-details.txt` record the persisted finish, assembly and remarks. `cart-item-scope.json` establishes that the visible C423131/C18548052 stock warning belongs to the pre-existing **Y22 15-board reorder**, which was left untouched; the new Y24 item has no stock-warning banner. JLC's product-description detail renderer shows a missing-translation string for the selected research/other category; the submitted plain-language description is preserved in `final-quote.txt` and should be checked during checkout review.

The pilot paste export removes all 16 U6 apertures, while retaining every other paste aperture. The full AS7331 land pattern remains in canonical CAD for a later populated build. U6-DNP pilots have no UV/lux/ozone measurement; eventual AS7331 operation needs its driver and optical calibration.

`quote-before-upload-green.txt` records the prepared green-mask quote. `quote-before-upload.txt` is superseded historical evidence from the earlier mistaken no-mask interpretation. The previous LTR390 supplier draft must not be used with this new BOM/CPL.
