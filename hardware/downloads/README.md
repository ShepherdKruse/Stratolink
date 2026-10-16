# v1.1 KiCad downloads

Use KiCad 10. These files match the engineer-rerouted revision and the [16 October final review](../../analysis/v1_1_final_sweep_20261016/README.md) on the `review/hardware-v1.1` branch.

- [Complete KiCad project ZIP](stratolink-v1.1-kicad.zip?raw=true): board, schematic, strict project/rules, project libraries and custom 3D models. Extract everything and open `stratolink-v1.1/stratolink.kicad_pro`.
- [Parts library ZIP](stratolink-v1.1-libraries.zip?raw=true): `lib/`, `3d/`, `fp-lib-table` and `sym-lib-table`. Extract these beside the matching `.kicad_pro`, `.kicad_sch` and `.kicad_pcb` files. This ZIP does not replace the board or schematic.
- [Browse the footprint and symbol files](../pcb/lib/).
- [Current pilot assembly BOM and placement files](../gerbers/v1.1-final-20261016/README.md).

The library includes the added **R24, R25, R26, R27, C22, C23 and U8** footprints, plus the other project footprints and symbols. All 68 board footprint instances load through KiCad's native footprint reader, and all 63 model attachments resolve with the standard KiCad model library installed. Six standard 3D model paths use KiCad 10's installed model library; missing standard models affect the preview, not footprint loading.

## If KiCad says a footprint was not found

Open the extracted project through its `.kicad_pro` file. In **Preferences → Manage Footprint Libraries → Project Specific Libraries**, the entry must be:

| Nickname | Library path | Type |
|---|---|---|
| `lib` | `${KIPRJMOD}/lib` | KiCad |

The `lib` directory must be beside the project, with files such as `Stratolink_v1p1_R27_R_0805_2012Metric.kicad_mod` directly inside it. Keep the supplied library tables beside the project too. If the table shows an old directory, use the supplied project-specific table. Reopen the project after replacing an older library copy. Do not download only the board and schematic or mix them with the older v1 library.

The complete project already contains the routed v1.1 board. Updating a blank or older PCB from its schematic is not required to review that layout.

## Revision and verification

PCB SHA-256: `e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13`.

[manifest.json](manifest.json) records the source and ZIP-member hashes against the [current manufacturing manifest](../gerbers/v1.1-final-20261016/manifest.json). [Fresh extraction checks](verification.json) confirm all 68 footprint instances, including the seven reported missing parts, load from both bundles and all 63 model attachments resolve. The archives use the strict published project settings and preserve the current schematic cosmetics. User-specific editor files, backups and caches are excluded. U6 is present in CAD; the initial pilot assembly omits U6 only. These remain engineering review files; see [fabrication notes](../pcb/FABRICATION.md) before ordering.

From a matching review checkout, rebuild or verify the downloads with Python 3.9 or later:

```sh
python3 hardware/downloads/build.py
python3 hardware/downloads/build.py --check
```

The default source manifest is `hardware/gerbers/v1.1-final-20261016/manifest.json`. If your editor has changed project settings, use `--project /path/to/matching-review/hardware/pcb`. To reproduce an older revision, pass its manufacturing manifest with `--manifest /path/to/older/manifest.json` and its matching `--project`. The builder refuses any source file whose hash differs from the selected manifest. The earlier pilot manifest was checked to reproduce the previous download archives exactly.

To repeat native footprint/model loading after extraction, run `verify.py` with KiCad's bundled Python, `--scratch /path/to/scratch` and `--standard-models /path/to/KiCad/3dmodels`. It creates temporary extractions, writes `verification.json`, and leaves the CAD source untouched.
