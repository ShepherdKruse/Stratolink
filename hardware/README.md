# Hardware

KiCad source files for the Stratolink payload. Follow [hardware setup](https://stratolink.org/docs/hardware) for parts, assembly, and programming.

## Files

- [pcb/stratolink.kicad_pro](pcb/stratolink.kicad_pro): KiCad project.
- [pcb/stratolink.kicad_sch](pcb/stratolink.kicad_sch): schematic.
- [pcb/stratolink.kicad_pcb](pcb/stratolink.kicad_pcb): board layout.
- [pcb/lib/](pcb/lib/): component symbols, footprints, and models.
- [gerbers/production_files/](gerbers/production_files/): assembly BOM and component placement exports.
- [gerbers/gerber/](gerbers/gerber/): archived drill files and drill maps.

Check the board revision before ordering parts or manufacturing boards. Generate fabrication files from the schematic and layout you have reviewed; the archived exports are not a complete fabrication package.

The [flight acceptance notes](../docs/flight/acceptance.md) cover power, RF, and assembly checks. The [hardware docs](https://stratolink.org/docs/hardware) describe the current energy-store qualification limits.
