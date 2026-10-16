# Hardware

KiCad source files for the Stratolink payload. Follow [hardware setup](https://stratolink.org/docs/hardware) for parts, assembly, and programming.

## v1.1 downloads

- [Complete KiCad project and parts library downloads](downloads/README.md)
- [Current v1.1 board and fabrication notes](pcb/README.md)
- [Engineer reroute review and exact changes](../analysis/v1_1_engineer_review_20261015/README.md)
- [Pilot assembly BOM and placement files](gerbers/v1.1-pilot/README.md)

Download and extract the complete project, or copy the library bundle beside the matching KiCad files. The bundles include the added R24–R27, C22/C23 and U8 footprints.

## Files

- [pcb/stratolink.kicad_pro](pcb/stratolink.kicad_pro): KiCad project.
- [pcb/stratolink.kicad_sch](pcb/stratolink.kicad_sch): schematic.
- [pcb/stratolink.kicad_pcb](pcb/stratolink.kicad_pcb): board layout.
- [pcb/lib/](pcb/lib/): component symbols, footprints, and models.
- [gerbers/production_files/](gerbers/production_files/): assembly BOM and component placement exports.
- [gerbers/gerber/](gerbers/gerber/): archived drill files and drill maps.

Check the board revision before ordering parts or manufacturing boards. Generate fabrication files from the schematic and layout you have reviewed; the archived exports are not a complete fabrication package.

The [flight acceptance notes](../docs/flight/acceptance.md) cover power, RF, and assembly checks. The [hardware docs](https://stratolink.org/docs/hardware) describe the current energy-store qualification limits.
