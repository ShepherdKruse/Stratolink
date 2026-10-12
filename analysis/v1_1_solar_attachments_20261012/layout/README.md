# Solar anchor geometry study — 2026-10-12

**Final routed candidate:** see [IMPLEMENTED_CANDIDATE.md](IMPLEMENTED_CANDIDATE.md). The geometry below records the earlier exploration; its y76.5 positive-hole option was rejected in favor of courtyard-clear holes at y85.0.

Read-only feasibility against canonical microphone-free v1.1, Git `1aed52ff7af3d27aef6ff4b0ceba710c57dc6865`. No CAD files or UI state changed. This study proposes dimensions for routing exploration; it does not establish fit to an unmeasured solar panel, solder-joint strength, or fabrication release readiness.

## Recommended local region

Keep the board outline, 0.4 mm thickness, and all electronic component placements. Put structural ground contacts close to the original side connectors, slightly above them. The useful nominal notch center is **y54.5 mm**, about 3.53 mm above the old positive pads, with one mirrored open notch per edge. The former microphone space benefits the left side; the right side remains constrained by MS5611 U4 and long supply/UART/I²C traces.

Provisional geometry for a routing trial:

| Feature | Left side | Right side |
|---|---:|---:|
| Edge X near notch | 53.3165 | 76.6755 |
| Notch center Y | 54.5 | 54.5 |
| Notch width along Y | 1.0 | 1.0 |
| Notch depth into board | 1.5 | 1.5 |
| Inner rounded tip X | 54.8165 | 75.1755 |
| Ground-land inward limit X | 55.6165 | 74.3755 |
| Ground-land Y range | 52.8–56.2 | 52.8–56.2 |
| Copper setback from routed cut | ≥0.20 | ≥0.20 |

Dimensions in millimeters. The ground land is a U shape around the cut, on both faces; it must be tied through ordinary plated holes beside the cut. It is **not plated on the routed wall**. Root research found JLC's edge-plating/castellation thickness restriction makes a plated-edge implementation incompatible with retaining the 0.4 mm board. The notch width and depth are provisional until the actual polymer sheet and metal-strip geometry are measured. Do not assume a closed plated slot can accept the middle of a continuous metal strip without cutting the panel.

This cut/land envelope clears all retained component pads in the geometry screen. It cuts left +SOLAR/VSTOR tracks and right VSTOR/PB5/RX/TX tracks. The right ground lands additionally displace +SOLAR. Ground pours also need refill. At y54.5, the contact is above U4's top right pad copper (starts y56.668) and below R15's last pad copper (ends y51.975), which gives better fan-out room than moving the contact lower. A full native DRC and pad-connectivity comparison is required after any route trial.

`open_notch_layout.png` overlays the proposed notch and lands over **existing** copper. Overlaps in this illustration are the routes to change, not a finished layout.

## Lower positive wire holes

A matched pair at **(54.3,76.5)** and **(75.7,76.5)** gives 22 mm vertical separation from the proposed ground notch. A 1.4 mm circular land with a proposed 0.7 mm finished drill clears all retained component pads at the study's 0.20 mm copper spacing. It leaves about 0.28 mm copper-to-board-edge margin. It requires local left GND and right +3.3 V/GND track changes.

These holes overlap the **empty bottom courtyard of J3/J4**, whose seventh pad centers are y75.174 and y75.158. They are suitable only if those rows are bare service pads, or the selected/retained actual header bodies permit the holes; do not dismiss the courtyard overlap automatically. A 1.6 mm land at the same height does not preserve 0.20 mm clearance to pad 7. Fully courtyard-clear 1.6 mm alternatives are asymmetric: roughly (54.5,79) and (75.5,82), which is less desirable for equal brace geometry.

Long +SOLAR feed corridors on B.Cu at x53.65 and x76.325, y58–76.5, clear every retained component pad. The right corridor has no track conflict; the left conflicts with PA9. However, both straight routes fail the required edge clearance at the old copper-wire support holes near y64. Those are Edge.Cuts circles, not pad objects:

- Left center (54.792,63.990), radius about 0.9724 mm.
- Right center (75.215,63.992432), same radius.

If retained, route around their inner sides (approximately x≥56.09 on the left, x≤73.918 on the right for a 0.25 mm trace and 0.20 mm edge clearance). If the new ground notches replace the original wire mount, removing these two obsolete support holes simplifies routing and strengthens the side webs; estimated added FR-4 is only **4.4 mg total** at 0.4 mm and 1.85 g/cm³. This study has not removed them or established whether the user needs them for another purpose. The two top suspension holes remain.

## Back capacitor and top alternative

The large rear C5 body is x57.875–71.875, y49.707–79.707 mm. Its courtyard is x56.875–72.875, y43.457–80.707. The middle side contact lands remain outside that envelope. Existing native 3D views support that clearance; panel bend, solder fillet, and external wire sweep still need an assembly mockup.

Moving the contacts up near y39 interferes with the corrected TMP117 U5 neighborhood, including its courtyard and SDA/SCL routing. Near y34.5 there are fewer electronic obstacles, but the land approaches the top suspension-hole rim: the bottom of a top hole is about y33.096, so a y34.5±1.7 mm land intrudes that margin. Top contacts also sit closer to the GNSS antenna and power harvesting circuitry. Thus moving to the top does not offer a clear low-risk v1.1 advantage.

Removing the microphone created local space, not an empty full-width strip that can simply be cut from board height. The GPS, MS5611, support holes, MCU, rear capacitor, and intervening supply/logic routes still set the length. A shorter/thicker board is a separate placement and routing redesign, even if its calculated laminate mass looks attractive.

## Reproduce and limitations

Run from repository root with `analysis/.venv/bin/python`:

1. `analysis/v1_1_solar_attachments_20261012/layout/study.py`
2. `analysis/v1_1_solar_attachments_20261012/layout/open_notch.py`
3. `analysis/v1_1_solar_attachments_20261012/layout/lower_positive.py`

`candidate_screen.json`, `open_notch_screen.json`, and the two lower-hole screen files contain exact track UUIDs and retained component conflicts. `candidate_screen.json` stores the source PCB SHA-256. These scripts read the pinned microphone-removal Git revision, so rerunning after an ECO reproduces the original feasibility screen without reading or editing the new canonical design.

Screens use actual copper geometry with Shapely at 0.20 mm spacing; rectangle pads are conservative, zones are excluded, and plots are reconstructed geometry rather than a native Gerber rendering. Mechanical top-hole and rear-cap constraints are reported separately. Native KiCad DRC/ERC, filled-zone connectivity, drill/outline export, and actual panel measurements remain controlling. Some project checks are currently disabled and must be enabled in a diagnostic copy when validating the mount.
