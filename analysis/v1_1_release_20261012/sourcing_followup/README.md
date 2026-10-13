# October 13 sourcing and placement follow-up

The canonical project is `hardware/pcb` on `alpha/hardware-v1.1`. The five-file R4/U2 sourcing update is promoted; no UV design or population change is included. The complete earlier implementation remains recorded at checkpoint `1cac1bb`.

| Item | Current result |
|---|---|
| R4 | YAGEO RC0402FR-073M65L / C477700 replaces the unavailable exact orderable, preserving 3.65 MΩ and the existing lands/nets. |
| U2 | RAK3172-8-SM-NI / C5452091 replaces the unavailable 9-labelled module. Manufacturer documentation establishes the same regional hardware; retain the NI RF-pad variant. This does not transfer certification labels or qualify 433 MHz operation. |
| U2 supplier placement | Explicit CPL90 reimport now agrees with numbered pads, pin 1 and all asymmetric pad groups. Native KiCad placement is unchanged. |
| UV | LTR390 remains in CAD while multiband selection is unresolved. AS7331 is the preferred integrated research candidate; direct LCSC checks found no available suitable integrated part. The external detector route and its limitations are documented. |
| Supplier draft | 56 references detected, 55 selected, U6 is the sole inventory shortage. No pilot has been added to the cart and no checkout or payment occurred. |

The uploaded replacement BOM and rotation-probe CSV are byte-identical to the newly regenerated canonical package's BOM and CPL. JLC's fabrication upload still contains the preceding ZIP (`a4025099…`). The regenerated local ZIP (`c4948f46…`) has different native creation timestamps; its copper, mask, paste, silk, outline and drill content otherwise matches. Upload the final matching package after the UV design/population is resolved, then complete missing-part placement and supplier review before the authorized cart addition. Do not treat the temporary preview without U6 as an approved DNP decision.

[Promotion and native verification](promotion.json) records 160 verified source inputs, 28 output hashes, the same four silk warnings, zero opens/parity/library issues and zero filtered ERC findings. All 100 unrelated tracked changes were preserved. Root reopened the updated canonical PCB in KiCad and independently rechecked those hashes afterward. [Native review view](canonical-kicad-reopened.png).

- [Quick/manual board change checklist](../manual-review-changes.md)
- [Integrated UV research and sourcing](../uv_followup/README.md)
- [Discrete detector option and signal/power model](../uv_followup/discrete-lcsc.md)
- [Radio compatibility](../radio_sourcing/README.md), [R4 equivalence](../radio_sourcing/r4-equivalent.md)
- [Independent U2 placement attestation](../radio_sourcing/u2-supplier-orientation-review.md)
- [Current supplier draft capture](current-draft-55-selected.txt)

Live inventory captures are observations from October 13, 2026, not reservations. Historical reports retain their original snapshots; this follow-up describes the current sourcing state.
