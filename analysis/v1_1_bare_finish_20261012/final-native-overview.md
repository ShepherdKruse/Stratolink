# Final native KiCad overview

[Overview](final-native-overview.png) rendered from the integrated candidate PCB SHA-256 `c0278f66e3eae9c135da38b97afaa241990706feb0ae730cbd5dc9a1a9ee4603`, using KiCad 10.0.0. It shows the exposed mainboard, both curved solar panels and leads, the shorter 48 mm GNSS wire above the board, and the longer 82 mm 915 MHz LoRa wire below it. Wire lengths are documented nominal assembly dimensions, not completed RF tuning. Native copper colors illustrate exposure rather than specifying a surface finish.

The integrated candidate was copied into `~/Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask/final-render`; the existing tracked `hardware/pcb/3d` directory was copied alongside its project files so the solar models resolve. No source CAD was modified. Native rendering reported no missing-model warnings, and the output was visually checked for both wire endpoints, panels and bare copper. The [manifest](final-native-overview.json) records source and image hashes.

Reproduce from the repository root after making that scratch copy:

```sh
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb render \
  --width 2400 --height 2100 --side top --zoom 0.25 --quality basic \
  --background transparent --rotate '30,0,0' \
  --output analysis/v1_1_bare_finish_20261012/final-native-overview.png \
  /Users/twarn/Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask/final-render/stratolink.kicad_pcb
```

The earlier front/back images under `mask/` document the mask-only candidate before the antenna-model correction; use this integrated overview for the completed geometry.
