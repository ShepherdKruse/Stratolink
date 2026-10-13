# AS7331 sourcing through JLC: three assembled pilot boards

2026-10-13. **JLC supports both Global Sourcing and customer consignment when its public stock is unavailable. Neither service makes an unavailable AS7331 immediately selectable for this draft.** The exact part must be obtainable, accepted for assembly and received into JLC inventory first. This read-only review checked official JLC help using the previously authorized web fallback; no RFQ, message, part request, shipment registration, order or payment was submitted.

## The three routes are different

| Route | Who buys the components? | What this means for AS7331 |
|---|---|---|
| JLC public-library pre-order | JLC replenishes a listed orderable | Out-of-stock extended parts have a part-specific MOQ and a later confirmed price. It is not the same as ordering exactly three from public stock. |
| Global Sourcing | JLC purchases from its offered global distributors | In Parts Manager → Order Parts → Global Sourcing, search the exact manufacturer part number and inspect supplier, packaging, available quantity, MOQ and lead time. The component order is separate from the PCB assembly order. |
| Consignment | We obtain genuine parts externally, then send them through JLC's registered receiving process | Useful if a verified source has stock that JLC cannot procure. It adds shipping, receiving and potentially import fees. The actual shipment origin determines the correct workflow. |

Sources: [JLC private-library/pre-order guide](https://jlcpcb.com/help/article/how-to-build-your-own-parts-library-in-jlcpcb), [Global Sourcing workflow](https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service), [parts-sourcing overview](https://jlcpcb.com/help/article/pcba-parts-sourcing-instruction).

JLC's matching guide says pre-ordered, globally sourced or consigned parts must have arrived and been selected in the component-matching interface before work can proceed. A catalog part with zero stock can therefore be sourced by a separate route, but a zero-stock BOM line is not a reservation or sourcing instruction. The current draft can be retained while sourcing is investigated; this review does not establish that it can be finalized with a pending AS7331. [Component Matching Guidelines](https://jlcpcb.com/help/article/component-matching-guidelines-for-pcba-orders).

The generic workflow quotes 1–3 business days for review and normally 9–20 business days for purchasing. Those are not an AS7331 availability promise: supplier backorders and the exact quoted lead time control. The previously checked distributors were out of stock, so Global Sourcing still needs an actually obtainable source. [Workflow and status descriptions](https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service).

## Quantity and packaging

Three populated boards need three usable sensors **plus the accepted attrition allowance**, rounded to the distributor's MOQ/order multiple. JLC publishes no universal AS7331 allowance in the checked help. Do not assume three pieces suffice, or invent a mandatory four/five/ten-piece quantity. Determine it from the exact orderable's Parts Calculator/component matching and the accepted packaging. The terms explicitly require spares and warn that globally sourced shortages of fewer than three pieces may be refunded instead of replenished. [Private-library guide](https://jlcpcb.com/help/article/how-to-build-your-own-parts-library-in-jlcpcb), [Global Sourcing terms](https://jlcpcb.com/help/article/global-sourcing-parts-order-terms-conditions).

Preserve original carrier tape and moisture-sensitive packaging when purchasing externally; retrieve the exact packing instructions within the consignment workflow. Loose pieces are accepted with added handling charges, but package condition and shelf life must be suitable. For AS7331, record the exact suffix/reel form and approved OLGA16 assembly identity; an evaluation board is not an assembly substitute. [Consignment terms](https://jlcpcb.com/help/article/consignment-part-terms-conditions), [Mainland consignment instructions](https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb-from-mainland-china).

## Fees that can and cannot be budgeted now

Global Sourcing terms say ordinary inbound shipping has no separate charge, with oversize exceptions, and sourced prices can differ from distributor retail. Loose components with more than five pins can incur up to $0.078 each; large/difficult pieces can incur $0.142 each. Optional baking is listed at $8 per 48 hours. These are possible service charges, not an AS7331 quote or evidence that baking is required. No fixed universal Global Sourcing percentage markup was verified. Paid parts orders generally cannot be cancelled or returned, subject to the unsupported-assembly exception. [Global Sourcing terms](https://jlcpcb.com/help/article/global-sourcing-parts-order-terms-conditions).

**Overseas-consignment fees are inconsistent across JLC's own current pages.** The Overseas Component Consignment User Guide specifies a nonrefundable handling charge of 2% of declared value, minimum $10 per shipment, plus a deposit for applicable import duty and 13% VAT on value plus duty; it describes refunding the import deposit after use in assembly. Yet the Consignment Terms page still lists $70 per 50 part numbers plus $15 handling—$85 for one to 50 types—plus taxes/duties. Both pages show September 9, 2026 updates. Do not silently combine these schedules or promise the lower one; the actual reviewed consignment fee breakdown must resolve which applies. External freight and assembly fees are additional. [Overseas guide](https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb), [Consignment terms](https://jlcpcb.com/help/article/consignment-part-terms-conditions).

For parts physically shipped within Mainland China, the documented receiving path is Zhuhai; for outside Mainland China, including Hong Kong/Macao/Taiwan as origin, it is the designated Hong Kong path. Do not choose origin based on the distributor's brand or billing address. JLC requires registration and purchase-invoice details. The mainland guide says no payment is required at its awaiting-payment registration step; that does not waive later assembly/handling charges. [Mainland guide](https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb-from-mainland-china).

## Practical decision

For a future AS7331 revision, inspect an exact Global Sourcing offer first; it avoids arranging our own overseas consignment if JLC can obtain a small accepted quantity. If a trustworthy external distributor has stock that JLC cannot offer, consignment is a real fallback, after receiving approval and resolving the fees. **No exact AS7331 MOQ, spare count, payable price, accepted source or delivery date was verified in this bounded review.** The separate footprint/routing/firmware change remains necessary; the present LTR390 footprint does not become compatible through sourcing.

For the current three-board pilot, these routes establish a way to obtain a future multiband instrument, not an immediate resolution of the UV line. See [the UV design review](README.md) and [the discrete-detector alternative](discrete-lcsc.md).
