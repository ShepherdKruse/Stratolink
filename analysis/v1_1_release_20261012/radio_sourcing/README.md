# U2 sourcing review — 2026-10-13

**Recommend RAK3172-8-SM-NI / C5452091 for this pilot as a metadata-only substitution.** It preserves the existing module family, oscillator, external antenna connection and land pattern. The live JLC search captured by the parent shows 444 public parts, five idle parts, and an enabled Select action; this is stronger assembly evidence than a distributor stock count. Selection, final placement preview and allocation belong to the parent’s supplier workflow. [Captured JLC search](../sourcing_followup/radio-jlc-search.txt)

RAK’s current store explicitly distinguishes regional certification labels from hardware: the regional variants use the same hardware. Its separate antenna-interface note says the MHF/IPEX option changes the RF path and disconnects the module RF pad. Applied specifically to the two high-band, non-T, NI part numbers, this supports an 8-to-9 functional substitution. It does **not** transfer the original regional certification marking or imply that the low-band hardware is identical. [Manufacturer’s variant clarification, notes 3–4](https://store.rakwireless.com/products/wisduo-lpwan-module-rak3172)

## Actual board and firmware

Read-only native KiCad extraction of PCB SHA-256 `490af47db22ef076938c17319782f194623d8f8b6a3f864a2e0cc23b3d025b15` found 32 U2 pads. RF pad 12 belongs to the physically connected set **U2.12, AE1.1, D1.2**, using six copper conductors. There is no separate coax route. Therefore an IPEX module would leave the intended PCB antenna disconnected inside the module. Pad positions, sizes and nets are recorded in [native-u2.json](native-u2.json); [extract_native_u2.py](extract_native_u2.py) regenerates the read-only check.

The existing U2 footprint origin is `(72.715,64.660)` mm, front side, 180°. The production CPL uses the reviewed package center `(64.950,−72.205)` mm at 180°. The differing coordinates reflect the footprint’s non-centered origin, not a reason to shift the replacement. Preserve the land pattern and reviewed center; recheck the replacement’s actual supplier preview because its model zero angle may differ.

Stratolink programs the STM32 directly with its own Arduino/RadioLib firmware, rather than relying on the factory AT-command configuration. `firmware/platformio.ini` selects the RAK3172 module and RadioLib 7.6.0. `firmware/src/lorawan.cpp` selects `REGION.init_freq`, drives the existing PB8/PC13 RF switch table, and calls `radio->begin(...,1.7f,false)`. The installed 7.6.0 `STM32WLx.cpp` passes the oscillator argument through; `SX126x.cpp:1452–1478` attempts TCXO startup and retries XTAL on the relevant oscillator error. That fallback is not evidence that an untested TCXO module is qualified. For the base NI high-band substitution, no changed pin mapping, oscillator family or configured radio region was identified. Source hashes are in [observations.json](observations.json).

## Variant disposition

| Part | Disposition for this PCB |
|---|---|
| RAK3172-9-SM-NI | Exact current part; preferred if available without procurement delay. |
| **RAK3172-8-SM-NI** | **Recommended available equivalent**, retaining base oscillator and NI antenna path; different regional label. |
| RAK3172-9-SM-I / -8-SM-I | Reject: connector variant disconnects RF pad 12. |
| RAK3172-T-9-SM-NI / -T-8-SM-NI | Same base/T 32-pad drawing; ±2.5 ppm TCXO. Requires oscillator, boot and cold RF qualification. |
| RAK3172-TE-9-SM-NI / -TE-8-SM-NI | TCXO version with ±0.5 ppm accuracy; same qualification issue. |
| RAK3172-F | Different 40-pin numbering and MCU/flash implementation; not approved by this review. |
| RAK3172-SiP or incomplete “RAK3172-9-SM” listing | Not an exact NI 32-pad identity; do not substitute from a family name alone. |

The datasheet groups 8xx/9xx regions under high-band RAK3172(H), separately from low-band 433/470 hardware. Base/T supply is 2.0–3.6 V; base operating temperature is **−20…85°C**, T is −40…85°C. Storage rating is not an operating guarantee. RAK supplies distinct base/T/F firmware images. These facts prevent generic distributor “−40°C” or “IPEX” descriptions from overriding the exact part identity. [RAK datasheet, pin definitions, RF characteristics, environmental and firmware sections](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/)

## Exact-part sourcing fallback

The opened US DigiKey page for **RAK3172-9-SM-NI** showed **1,388 available**, cut tape `4735-RAK3172-9-SM-NICT-ND`, MOQ 1, $10.27 at one and $8.917 at ten. This can support exact-part global sourcing or consignment if JLC accepts it; it is not allocated JLC inventory. [DigiKey exact part](https://www.digikey.com/en/products/detail/rakwireless-technology-limited/RAK3172-9-SM-NI/17138034)

Opened LCSC pages showed **one** C18548052 and **383** C5452091; stale search snippets gave different counts and were discarded. JLC’s actual assembly search remains controlling for this pilot. [Exact -9 LCSC listing](https://www.lcsc.com/product-detail/C18548052.html), [exact -8 listing](https://www.lcsc.com/product-detail/C5452091.html)

No order, external message, CAD edit or firmware edit was made by this review. The subagent’s in-app browser listed zero connected instances, so primary-source web fallback was used under the parent’s explicit authorization; the active JLC quote tab was untouched. This is a sourcing/compatibility decision, not a replacement for the already-required assembled-board boot, TX/RX, cold and supply tests.
