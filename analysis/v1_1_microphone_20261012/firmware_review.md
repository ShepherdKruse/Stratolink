# Microphone removal: firmware review

Reviewed and implemented 2026-10-12 on `alpha/hardware-v1.1`, starting at `38de8d7`. Only `firmware/src/mic_acoustic.cpp` and `firmware/platformio.ini` were changed for this disposition; both were clean before editing. Existing dirty `firmware/src/main.cpp`, `firmware/include/config.h`, and all unrelated firmware/web work were preserved. No device was flashed.

## Initial finding

The existing v1 flight image does **not** disable the microphone automatically when it is absent. This change adds the required explicit microphone-absent variant. The table below records the pre-change source locations; the v1 driver itself is unchanged inside the new conditional branch.

| Evidence in the current working tree | Consequence |
| --- | --- |
| `firmware/platformio.ini:42` and `:74`: the base flight build has no microphone presence flag and includes `mic_acoustic.cpp` through `+<*>`. `firmware/include/config.h` has no microphone gate. | A compiler `-D` on its own cannot disable the existing code; a small source gate is required. |
| `firmware/src/main.cpp:457`: `(void)mic_acoustic_init()` is unconditional. | Every ordinary flight boot configures the microphone peripheral. |
| `firmware/src/mic_acoustic.cpp:45–66`: init enables GPIOB and SPI1, configures PB3/PB4 as AF5, sets PB3 to very-high speed, and returns true without probing a sensor. | Init success is not evidence of a fitted microphone. |
| `firmware/src/main.cpp:787–788`: each allowed sensor cycle assigns `acoustic_valid` from `mic_acoustic_detect()`. `firmware/src/power_adc.cpp:205–206` permits sensor reads through the NO_GPS tier. | Capture remains active during normal powered cycles, not merely during a special acoustic diagnostic. |
| `firmware/src/mic_acoustic.cpp:59–63`, `:95–123`: SPI1 is receive-only **master** and generates its own 3 MHz clock; RXNE is checked for every received byte. | A missing microphone does not stop the SPI master shifting electrical input samples. The RXNE timeout bounds a stalled peripheral but is not a microphone-presence test. |
| `firmware/src/mic_acoustic.cpp:140–159`: completed transfers become a variance threshold result and return true. | A disconnected PB4 may yield valid-looking quiet or spurious acoustic events depending on its electrical state. Neither is a valid acoustic observation. |

The current capture consumes approximately 318 ms per allowed sensor cycle from its programmed geometry: 18,750 wake bytes plus `(2,000 + 512) × 40` sample bytes, at 375,000 bytes/s, equals **0.3179467 s**. The MCU clock-generation/capture overhead persists even without the mic. This is a code-derived timing estimate, not a measured energy saving.

PB3 remains an alternate-function output and PB4 an alternate-function input after capture; capture only clears SPI1 SPE (`mic_acoustic.cpp:125–128`). No microphone-specific analog-pin cleanup was found in `power_manager.cpp`. With the CAD clock resistor and microphone trace removed, PB3 would still toggle the exposed MCU pad and any retained copper stub; PB4 would have no microphone driver.

## Implemented disposition

`firmware/platformio.ini:78` now defines `env:stratolink_v1_1`, which inherits the existing `stratolink` configuration and adds `-D STRATOLINK_MIC_PRESENT=0`. The gate at `firmware/src/mic_acoustic.cpp:18` defaults to 1, preserving existing v1 builds. Existing callers and the packet format are unchanged:

1. The absent-hardware implementation of `mic_acoustic_init()` configures PB3/PB4 as analog inputs with no pulls, enables no SPI1 peripheral, and returns false (`mic_acoustic.cpp:25`).
2. Its `mic_acoustic_detect()` writes `0` to a non-null event pointer and returns false immediately (`:33`). No clock, capture wait, or noise-floor update occurs.
3. The fitted-hardware implementation remains as it is for existing v1 boards. The mic diagnostic environment is for fitted boards. No new function is assigned to the freed PB3/PB4 pins.

This avoids edits to the already dirty flight main loop and keeps hardware revision selection explicit. The no-mic variant omits microphone capture diagnostics from its binary because there is no capture path; exact-ELF diagnostics must use the ELF for the chosen hardware variant.

The current working tree already represents absence correctly on the wire: `telemetry_input_init()` zero-initializes `acoustic_valid` (`firmware/src/telemetry.cpp:39–41`), and `telemetry_pack()` emits unavailable status codes 10–14 when it is false (`:69–81`). `firmware/test/ttn_uplink_formatter.js:92` and `web/lib/ttn/payload-parser.ts:635` decode those v2 codes to `null`; there is no need to shrink the packet or make missing hardware look quiet. This conclusion applies to the reviewed working tree, not an assumed previously flashed binary.

Build v1.1 from `firmware/` with `~/.platformio/penv/bin/platformio run -e stratolink_v1_1`; use `-e stratolink` for the existing v1 hardware. These are build commands only.

## Verification

- `python3 analysis/v1_1_microphone_20261012/test_no_mic_firmware.py` passed. It compiles the **production** no-mic driver and telemetry encoder against deliberately limited fake registers with no SPI API. It exercises four initial GPIO patterns, confirms only PB3/PB4 change, confirms analog/no-pull configuration and no capture-time register writes, checks null-pointer handling, and verifies unavailable status codes for all five power tiers.
- The actual STM32 `stratolink_v1_1` build passed: 7,624 bytes static RAM and 141,384 bytes flash. The selected dependency graph was GNSS 3.1.13, Low Power 1.5.0, RTC 1.9.0, and RadioLib 7.6.0.
- The existing `stratolink` build also passed: 7,660 bytes static RAM and 141,900 bytes flash. The no-mic variant therefore removes 36 bytes static RAM and 516 bytes flash in these builds. Both builds emitted the framework's existing Tone timer configuration warning; neither had a microphone warning or error.
- ARM object disassembly confirms `mic_acoustic_init()` touches only RCC AHB2 GPIO clock enable and GPIOB MODER/PUPDR; `mic_acoustic_detect()` only clears a non-null event byte and returns zero. No SPI1 operation remains in these no-mic functions.
- No firmware was flashed and no bench power saving was measured. A normal pilot bring-up still needs physical confirmation of the quiet pins and decoded unavailable field.

Ancillary observation: `firmware/include/stratolink_pins.h:112–134` describes DMA and a 2.4 MHz nominal clock; the actual fitted-microphone driver polls SPI at 3 MHz. Those stale v1 comments are outside this removal; no disabled-path behavior depends on them.
