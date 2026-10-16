# AS7331 sourcing for the first three v1.1 boards

Checked October 16, 2026 through the signed-in JLC sourcing portal, DigiKey and manufacturer pages. The reviewed v1.1 design already supports U6 AS7331. External procurement is possible in principle, but **no immediately available bare sensor was found in the sources checked**. The saved Y25 assembly remains UV-DNP; no purchase, shipment registration, sourcing inquiry or cart change was made during this review.

## Current availability

| Source | Observed result | Implication |
|---|---|---|
| [DigiKey AQFM](https://www.digikey.com/en/products/detail/ams-osram-ag/AS7331-AQFM-OLGA16-LF-T-R/16983757) | 0 stock; 1,000 expected November 9, 2026; cut tape $9.16 at 1, $8.278 at 5, $7.95 at 10 | Small quantities are listed, but this is a backorder, not stock ready to ship. Expected replenishment is not a delivery commitment. |
| [DigiKey AQFT](https://www.digikey.com/en/products/detail/ams-osram-ag/AS7331-T-OLGA16-LF-T-RDP/16983752) | 0 stock; 4,951 expected November 9, 2026; same small-quantity prices; another 49 estimated July 19, 2027 | Same package, alternate reel orderable. No immediate supply advantage. |
| [JLC Global Sourcing](https://jlcpcb.com/user-center/smtPrivateLibrary/orderParts/?global=1), search `AS7331` | AS7331 evaluation kits from DigiKey, RS and Mouser; unrelated Glenair connector; no bare AS7331 offer. Expanded results repeated those offers. | The evaluation kit is not the component to put on the PCB. No usable live sourcing quote. |
| JLC Global Sourcing, exact `AS7331-AQFM` and `AS7331-AQFT` | Both returned no result and offered a new-part request | Manual sourcing inquiry is the next route to an exact JLC quote. |
| [ams OSRAM ordering page](https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7331-spectral-uv-sensor) | AQFM Q65114A3064 and AQFT Q65114A3065 both labeled pre-production; AQFT offers a sample-request link | Manufacturer inquiry could clarify supply, but neither free samples nor immediate availability is established. Distributor Active labels do not resolve this discrepancy. |
| Mouser direct | Access denied by the site | No fresh direct stock or price assertion. October 13 observations remain historical. |

AQFM and AQFT differ in the documented 1,000 versus 5,000-piece reel quantity; the manufacturer lists the same OLGA16 device and marking. A distributor's cut-tape minimum can be much smaller than the factory reel. See [assembly readiness](assembly-readiness.md).

## Best procurement route

First request **JLC Global Sourcing of genuine cut-tape AS7331**, with AQFM preferred and AQFT an explicitly documented alternative. JLC purchases the parts and receives them directly. Its [current guide](https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service) says ordinary inbound shipping has no separate fee, with oversize exceptions; component prices may differ from distributor retail. The portal currently has no bare-device offer, so the DigiKey prices below are not JLC quotations.

Consignment is a fallback: we buy genuine parts and direct the approved shipment to JLC's designated receiving address. For overseas physical origins, the [overseas guide](https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb) requires registration, price documentation, approval and the designated Hong Kong address before dispatch. A mainland-origin shipment follows a different workflow. Do not send parts to an arbitrary JLC factory address or route them through the US unnecessarily.

**The fee conflict is still present in current official documentation.** Both pages display September 8, 2026 updates in this browser:

- Overseas guide: 2% handling, minimum **$10 per shipment**, plus import-duty and 13% VAT deposits. Deposits are described as refunded after components are used in assembly; unused spares may remain in inventory.
- [Consignment terms](https://jlcpcb.com/help/article/consignment-part-terms-conditions): **$70 per 50 part numbers plus $15 handling**, therefore **$85 for one part type**, plus taxes/duties.

These are competing published schedules. Do not add them together or assume the cheaper one applies. The actual reviewed quote must resolve this before payment. External freight and additional assembly charges remain separate.

## Budget, not a payable quote

| Purchase quantity | DigiKey listed component subtotal | Subtotal plus $10 handling scenario | Subtotal plus $85 handling scenario |
|---|---:|---:|---:|
| 3 | $27.48 | $37.48 | $112.48 |
| 5 | $41.39 | $51.39 | $126.39 |
| 10 | $79.50 | $89.50 | $164.50 |

Three pieces only covers three placements and provides no loss allowance. **Five is a budgeting example, not a verified sufficient quantity.** JLC must specify the accepted attrition count, minimum assembly quantity, tape/leader format and purchasing minimum for this exact device. Ten is a sensitivity case, not a recommendation.

All scenario figures exclude freight, import deposits/taxes, any reeling, moisture handling and added PCBA charges. DigiKey lists a **$7 Digi-Reel fee** if that service is needed. JLC lists optional baking and loose-component handling; neither is assumed necessary for factory-sealed compliant tape. Under only the lower fee scenario and an assumed zero import-duty rate, the five-piece 13% VAT deposit would be $5.38. The applicable duty rate and refund timing are unverified.

The saved PCB/assembly draft was $332.63 before delivery/tax/manual review supplements. Adding the five-piece component-plus-handling scenarios gives **$384.02 or $459.02**, still before the exclusions above. These are arithmetic planning totals, not revised JLC cart prices.

November 9 is 24 days after this review. JLC's generic 1–3-business-day review and 9–20-business-day purchasing descriptions do not establish an AS7331 production date. Receiving, inspection and assembly follow actual supply. A late-November or December finished-board date would be a planning possibility, not a promise.

## Assembly impact and next action

The frozen reviewed board needs an assembly variant, not another UV layout redesign. The new package would contain **58 fitted references**, restore **16 U6 paste apertures**, and receive a fresh exact-part orientation check. Existing support components remain. AS7331 firmware and optical calibration still need qualification before useful flight measurements; fitting the chip alone does not establish an ozone estimate.

The live CAD was edited after the saved Y25 export. Preserve those edits and reconcile the source before creating a populated export. Details, including a removed VSTOR trace segment, are in [assembly readiness](assembly-readiness.md). No live CAD changes were made during sourcing research.

Recommended next action: obtain one written JLC quote for three assembled boards with the required spare quantity, using Global Sourcing first and approved consignment as fallback. The [ready-to-send inquiry](jlc-inquiry-draft.md) contains the exact parts, source links and unresolved cost questions. It has **not been sent**. Keep the current draft until supply and the total incremental cost are confirmed.

## Evidence

The adjacent `.txt` files are rendered page-text captures, not API inventory guarantees. URLs and review date are recorded above; stock and expected dates can change. `evidence-manifest.json` records file hashes. Earlier [October 13 research](../v1_1_release_20261012/uv_followup/procurement.md) predates the AS7331 hardware conversion and must not be used to claim the current board still has an LTR390 footprint.
