# v1.1 KiCad downloads

Use KiCad 10. These files match the engineer-rerouted revision on the `review/hardware-v1.1` branch.

- [Complete KiCad project ZIP](stratolink-v1.1-kicad.zip?raw=true): board, schematic, strict project/rules, project libraries and custom 3D models. Extract everything and open `stratolink-v1.1/stratolink.kicad_pro`.
- [Parts library ZIP](stratolink-v1.1-libraries.zip?raw=true): `lib/`, `3d/`, `fp-lib-table` and `sym-lib-table`. Extract these beside the matching `.kicad_pro`, `.kicad_sch` and `.kicad_pcb` files. This ZIP does not replace the board or schematic.
- [Browse the footprint and symbol files](../pcb/lib/).
- [Pilot assembly BOM and placement files](../gerbers/v1.1-pilot/README.md).

The library includes the added **R24, R25, R26, R27, C22, C23 and U8** footprints, plus the other project footprints and symbols. All 68 board footprint instances load through KiCad's native footprint reader, and all 63 model attachments resolve with the standard KiCad model library installed. Six standard 3D model paths use KiCad 10's installed model library; missing standard models affect the preview, not footprint loading.

## If KiCad says a footprint was not found

Open the extracted project through its `.kicad_pro` file. In **Preferences → Manage Footprint Libraries → Project Specific Libraries**, the entry must be:

| Nickname | Library path | Type |
|---|---|---|
| `lib` | `${KIPRJMOD}/lib` | KiCad |

The `lib` directory must be beside the project, with files such as `Stratolink_v1p1_R27_R_0805_2012Metric.kicad_mod` directly inside it. Keep the supplied library tables beside the project too. If the table shows an old directory, use the supplied project-specific table. Reopen the project after replacing an older library copy. Do not download only the board and schematic or mix them with the older v1 library.

The complete project already contains the routed v1.1 board. Updating a blank or older PCB from its schematic is not required to review that layout.

## Revision and verification

PCB SHA-256: `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`.

[manifest.json](manifest.json) records the source and ZIP-member hashes. [Fresh extraction checks](verification.json) confirm all 68 footprint instances, including the seven reported missing parts, load from both bundles. The archives use the strict published project settings. User-specific editor files, backups and caches are excluded. U6 is present in CAD; the initial pilot assembly omits U6 only. These remain engineering review files; see [fabrication notes](../pcb/FABRICATION.md) before ordering.

From a matching review checkout, rebuild or verify the downloads with Python 3.9 or later:

```sh
python3 hardware/downloads/build.py
python3 hardware/downloads/build.py --check
```

If your editor has changed the project settings, use `--project /path/to/strict-review/hardware/pcb`. The builder refuses source files that differ from the verified manufacturing manifest.
