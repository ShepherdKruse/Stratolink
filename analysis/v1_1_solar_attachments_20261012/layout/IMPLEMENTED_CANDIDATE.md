# Routed solar-attachment candidate

Frozen candidate source SHA-256: `e502e2735535fe525f9699972b2be0dfbc038ae7773fc8da4003339f8e522ba0` (PCB). Built against `1aed52ff7af3d27aef6ff4b0ceba710c57dc6865` in scratch, then promoted byte-for-byte to the canonical `hardware/pcb/` project after independent review. See [promotion evidence](../review/final/promotion.json). The read-only geometry study in this folder contains earlier explored dimensions; this file describes the actual routed candidate.

- Board remains 0.4 mm thick and retains its exterior dimensions and 57 other footprints exactly.
- J1/J2 are custom manual-solder connectors. Each has separate F.Cu/F.Mask and B.Cu/B.Mask ground lands numbered 2, and one 1.4 mm plated positive pad with a 0.7 mm finished drill numbered 1.
- Two open unplated notches are centered at y54.5, each 1.0 mm wide and 1.5 mm deep, with R0.5 mm inner tips. Broad U-shaped ground lands span y53.1–55.9 and have a nominal 0.22 mm copper setback from the notch cut; this avoids the arc-to-polygon chord rounding that reported 0.1994 mm with a nominal 0.20 mm setback. Copper remains at least 0.20 mm from the outside edge.
- Each ground land pair is connected by two conventional 0.6/0.3 mm GND stitching vias. The notch wall is not plated. No paste apertures exist on these manual contacts.
- Lower positive wire holes are symmetric at (54.8,85.0) and (75.2,85.0), giving 30.5 mm separation from the notch centers. They clear the retained service-header and component courtyards. Explicit GND and + silk labels identify polarity.
- The two old side wire-support holes near y64 are removed; the top suspension holes remain.
- J1/J2 schematic pin numbering and net assignments are preserved. Value/footprint metadata is updated, stale JST datasheet/description text is cleared, and the manually soldered connectors are excluded from automated BOM/placement export. Project-local footprint files match the embedded board geometry.

## Routing scope

Local notch bypasses preserve +SOLAR, VSTOR, PB5, RX, TX, and SDA connectivity. The RX layer-change via is moved to clear the upper right ground land. The upper right front crossbars are at y52.330 (PB5) and y52.745 (VSTOR), which preserve the corrected R15 clearance without moving that resistor. The old microphone supply bridge remains intact.

Both lower positive holes share one +SOLAR feed down the left side and across the board's lower back edge. The left feed changes to the front layer through the existing service-header region to avoid crossing PA9, then returns to B.Cu below it. This avoids a second feed crossing the dense UART routes on the right. Two ground stitching vias move locally to clear the new supply route; obsolete ground corner stubs are removed and ground fill is regenerated. Newly created routing vias explicitly retain their assigned net during zone refill.

## Verification

Native KiCad 10 checks:

| Check | Frozen microphone-free baseline | Solar candidate |
|---|---:|---:|
| Project DRC findings | 73 | 70 |
| Enabled 0.15 mm net clearance / 0.20 mm edge diagnostic | 87 | 83 |
| Unconnected PCB items | 0 | 0 |
| Schematic parity findings | 11 | 11 |
| ERC findings | 55 | 55 |

No new shorts, hole-clearance issues, mask bridges, courtyard overlaps, starved thermals, or schematic parity findings were introduced. J1's old starved thermal and the two header/library mismatches disappear. The diagnostic also removes the old J2 positive-pad/GND clearance violation. The nine inherited edge-clearance findings involve unchanged copper against newly segmented straight outline edges; the exterior edge position changes by less than 0.001 mm. The four remaining diagnostic copper clearances are inherited.

All 57 retained footprints are byte-structurally equivalent under the independent parsed-object comparison. All 219 schematic net nodes remain unchanged. All 230 physical pad connectivity checks pass, including each front/back ground land separately reaching all original 67 GND logical nodes. The corrected TMP117 and microphone no-connects are preserved. See the independent `../review/` results and raw native reports in `validation/`.

This remains a prototype candidate, not a fabrication release: inherited DRC/ERC issues still exist, and the specific panel end strip must be dry-fitted and soldered on a coupon before ordering. The crossed-sheet mount seats the panel against one notch bank; the semicircular tip does not provide its full nominal depth as usable overlap against a straight bank.

`build_candidate.py` reproduces a disposable candidate from the fixed Git baseline. It writes only the scratch candidate path, never canonical hardware. Native refill and both validation passes must follow; UUIDs are newly allocated on rerun. The `validation/candidate_source_sha256.json` file identifies the reviewed outputs.
