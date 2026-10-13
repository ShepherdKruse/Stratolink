# Larger programming-wire lands

The selected candidate enlarges **only the back copper lands of J3/J4 to 1.20 × 0.88 mm**, offset 0.12 mm toward the board center. The **0.88 mm front lands, 0.50 mm holes, hole centers, 1.00 mm pitch, component positions and board outline remain unchanged**. Use the back face to tack temporary programming wires; the capacitor body is farther inward, and the existing front-side routing can retain its clearance.

The 12 oval lands gain **46.3% total land area**, or **68.4% exposed copper area after subtracting the hole**. The two rectangular pin-1 lands gain **36.4% total area / 48.7% net of the hole**. Pin 1 remains rectangular for orientation. Minimum nominal annulus stays **0.19 mm**. An ordinary PTH footprint with KiCad's native front/inner/back padstack encodes the different faces; the exported copper and drill files require no castellated-hole or edge-plating process.

Candidate: `~/Repositories/ai-working/scratch/stratolink-release-20261012/headers/candidate`, based on commit `59979799c5809d636639084227d9fee75c8de1d9`.

PCB SHA-256: `f83a344bb1bf817207c7a121dabbd4acb92815967c4ed870ca0c49b1698a56a8`.

## Why this geometry

Extending the front lands substantially inward collides with PB2 on the left and TX/RX on the right. Extending them outward approaches the recently corrected PA9/+SOLAR/VSTOR edge routes. Reducing land height to 0.86 mm would increase interpad clearance but reduce the minimum annulus to JLC's 0.18 mm absolute limit. Keeping 0.88 mm height preserves the existing 0.19 mm ring and approximately 0.12 mm neighboring-land gap, above the sourced 0.10 mm copper minimum for the chosen process. With no mask on either face, there is no mask-web requirement. See the [captured JLC capability rows](../../v1_1_edges_20261012/sources/jlc-capability-rows.json) and the parent's current supplier review.

Rear access makes a more useful increase possible with two contained signal-route adjustments. PB5's short back-layer detour next to J3.4 moves **0.04 mm inward**, keeping its 45° joins. The RX diagonal next to J4.4 becomes a short vertical/45°/horizontal path. Four existing segment endpoints change and two segments are added; all remain **0.25 mm wide**, with no new vias or changed endpoint pads. RAK placement, RF feeds and the edge runs remain unchanged.

The enlarged J3.2 GND pad initially lost a second valid thermal spoke. A **local 30° spoke-angle override**, replacing its measured native 90° default, restores the required two-spoke relief. It is applied to the reusable left footprint as well as the placed pad. This also changes the immediate front-side ground-relief orientation; front pad size and drill geometry remain the same. No global ground or mask settings change. Angles 0° and 22.5° failed the same spoke requirement, while 30° passed; the selected result has no starved thermal findings.

Castellations were not selected. The parent release research evaluates their supplier minimum thickness/cost against this 0.40 mm board. This change uses the existing full PTH drill process and adds no laminate. Added pad copper is 3.9424 mm² on the rear face, equivalent to **1.24 mg of copper** at the nominal 35 µm thickness before accounting for nearby zone-clearance changes. This is a pad-area estimate, not a measured finished-board mass.

## Verification

[Before/after plot](header-back-before-after.png) uses native KiCad copper polygons and was visually inspected. Ground fill is omitted in that plot to reveal wire lands and routing; verification uses the refilled zones.

| Check | Result |
| --- | --- |
| All physical pad connectivity sets | 232 identical; zero opens |
| Header hole centers, sizes and drills | Identical, including exported drill files |
| Front header pad copper | Identical native polygons |
| Rear neighboring-land minimum gap | 0.119999 mm |
| Header hole to foreign copper minimum | 0.309999 mm |
| Rear header copper to board outline | 0.648733 mm minimum |
| Changed routes to foreign copper | 0.141 mm minimum |
| Nominal minimum annulus | 0.19 mm, both faces |
| Project DRC | 55 before / 55 after; 51 existing library mismatches + 4 bare-board silk warnings |
| Enabled 0.10 mm clearance / 0.20 mm edge screen | Same 55 before / after; no copper-clearance or edge errors |
| Schematic parity | 11 existing findings, unchanged |
| Existing local library files | All 86 unchanged; two new programming footprints added |
| Paste, drill and board-outline exports | Identical |

The minimum routed gap of 0.141 mm is above the process screen and below the older blanket 0.20 mm class preference. Neither that preference nor the project rule severities are changed in this candidate. The final release review must retain a named, explicit fabrication-rule disposition rather than interpreting an unchanged project count as a complete fabrication qualification.

Detailed [scope and hashes](candidate.json), [native verification](verification.json), [per-pad/per-route measurements](geometry-review.json), [project DRC](candidate-drc-project.json) and [enabled process screen](candidate-drc-process.json) are included. B.Mask Gerber text changes because the rear pad aperture definitions follow the enlarged lands, but the existing full-face opening still supersedes all local apertures; no mask is reintroduced. F/B paste exports and all drill output remain identical.

Two new project-local footprints and the matching PCB/schematic `Footprint`, `Value` and `Description` metadata describe the actual 1 mm pitch and 0.50 mm holes. The former misleading 2.54 mm-pitch/D1 mm value is no longer used for these placed headers. Other symbols and identities are untouched. Native serialization reorders existing antenna graphics without changing their geometry.

## Reproduction

From the repository root, using KiCad's bundled Python for native CAD work:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/headers/build_candidate.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/headers/verify_candidate.py
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/headers/extract_baseline.py /Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/headers/candidate/stratolink.kicad_pcb candidate
analysis/.venv/bin/python analysis/v1_1_release_20261012/headers/measure_and_plot.py
```

The saved `native-audit.json.gz` is the Git-pinned baseline inventory. `extract_baseline.py` with no arguments recreates its equivalent as `baseline-geometry.json.gz`; the latter includes additional per-layer padstack metadata and can also serve as the baseline input to the measurement script. Temporary CAD remains outside the canonical repository; no hardware was ordered or uploaded.
