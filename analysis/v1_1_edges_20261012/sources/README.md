# Manufacturer constraints used for this step

Read the [current JLCPCB rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) in the Codex in-app browser on 2026-10-12. The relevant table rows are preserved in `jlc-capability-rows.json`. These limits apply to the intended two-layer, 1 oz, green-mask, routed FR4 process; they are not a complete fabrication release rule set.

| Feature | Published capability | Application here |
| --- | --- | --- |
| Copper to routed edge or routed slot | At least 0.20 mm | Move the flagged routes inward with additional nominal margin where local space permits. V-score's 0.40 mm rule is a different process. |
| Component PTH annulus, two-layer 1 oz | Recommended 0.25 mm; absolute minimum 0.18 mm | Existing J3/J4 nominal rings are 0.175 mm. Their 1 mm pitch prevents 1 mm diameter pads without touching neighbors. |
| Ordinary routing via | Land diameter at least 0.10 mm larger than hole, preferably 0.15 mm | Do not apply component-lead-hole ring recommendations to U1's thermal vias or ordinary routing vias. Classify by actual function and fabrication geometry. |
| Track width/spacing and pad-to-track gap, 1 oz | 0.10 mm | This is a local fabrication lower limit, not a reason to reduce every existing net-class rule. |
| Component PTH hole to track | Minimum 0.28 mm, recommended 0.35 mm | Check the actual hole rim against neighboring-net copper separately from pad-to-pad gap. |
| Component pad hole-to-hole spacing | 0.45 mm | Fixed 0.50 mm holes at 1 mm pitch retain 0.50 mm nominal hole-edge spacing. |
| Solder-mask expansion | A 1:1 opening is supported by the updated LDI process | Confirm actual exported openings; preserve a usable mask web rather than only copper clearance. |
| Green 1 oz mask bridge | 0.10 mm | Black/white have a larger 0.13 mm stated requirement; this geometry review assumes green. |
| Mask opening to neighboring trace | 0.09 mm | Review separately from mask-opening-to-opening distance. |

The table gives regular routed dimensional tolerance of ±0.20 mm and normal finished through-hole tolerance of +0.13/−0.08 mm. Nominal CAD distances are not measured finished-board distances. The supplier's design limits and fabrication tolerances should not be combined into a claim of guaranteed finished ligament or breaking strength. Existing 0.4 mm thickness and ENIG/BGA process considerations from the earlier review remain in force.

The original project stores a 0.50 mm copper-edge constraint but ignores its severity. Earlier diagnostic screens used 0.20 mm for the routed-edge capability. This step keeps those cases distinct and does not silently redefine the old rule or call the whole design DRC-clean. Header ring changes must be assessed with explicit geometry because the saved 0.10 mm annulus setting was sized for vias, not these component pads.
