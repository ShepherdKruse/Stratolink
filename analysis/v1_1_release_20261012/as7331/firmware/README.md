# Firmware population for the AS7331-layout pilot

Use **`stratolink_v1_1_uv_dnp`** for the initial assembly with **U6 absent**. It inherits the v1.1 microphone omission and charge-divider model, explicitly selects no UV sensor, and cannot issue LTR390 transactions or wait for an absent optical sensor. Temperature, pressure, acceleration, GNSS, and radio behavior remain the existing code's behavior.

| Hardware population | Build | Status |
|---|---|---|
| Flown v1 with LTR390 and microphone | `stratolink` | Existing target, unchanged |
| Earlier v1.1 layout with LTR390, no microphone | `stratolink_v1_1` | Existing target, unchanged; **not the new AS7331 PCB population** |
| New AS7331-layout pilot, U6 absent | `stratolink_v1_1_uv_dnp` | Selected pilot target; compilation and host integration passed |
| New layout with AS7331 populated | No supported target yet | Needs AS7331 initialization, conversion and verified power-down driver, raw multiband payload/decoder, and physical bring-up |

The DNP implementation retains the existing optical-function interface so no edits to the already modified flight loop, configuration or telemetry serializer are needed. Initialization succeeds for an intentional absence, reads return false without writing caller output, and quiescence succeeds without hardware access. The flight loop already calls `telemetry_input_init` for each cycle; UV and lux stay at their existing invalid sentinels (`0xfe`, `0xfffe`) instead of reporting zero or stale valid values. An actual failure of the remaining sensors still invokes their existing bounded shared-bus recovery. DNP is a population declaration, not automatic absence detection.

**Do not use the DNP image after fitting AS7331.** It does not initialize or establish the power state of a fitted AS7331. `STRATOLINK_UV_SENSOR=0` means DNP and `=1` means the legacy LTR390; all other values fail compilation instead of silently selecting either implementation. AS7331 has no visible-light ALS channel, and this patch makes no ozone or calibrated UV-index claim.

## Change and verification evidence

Only two firmware files changed: [platformio.ini](../../../../firmware/platformio.ini) and [sensor_ltr390.cpp](../../../../firmware/src/sensor_ltr390.cpp). The other **134 tracked firmware files** stayed byte-identical to the beginning of this work, including all pre-existing dirty firmware. See [the exact patch](population.patch), [before hashes](before.json), and [verification](verification.json). No commit or firmware flash was performed by this subtask.

- The existing `stratolink_v1_1` built before and after the patch with an **identical firmware.bin SHA-256**, `3d6b80c256949ec0e02d739a0eab2f3efca23aa2730bcc3928d602589eab1c43`. It uses 141,384 flash bytes.
- The new DNP image builds with **140,584 flash bytes and 7,608 RAM bytes**. This is build compatibility, not a new qualification of every pre-existing flight-firmware change.
- [The host test](test_uv_dnp.py) compiles the actual DNP driver, actual shared-sensor initialization, and actual telemetry initializer/serializer. Across **20,000 cycles** it verifies no optical I²C transactions or waits, invalid UV/lux wire values after earlier valid values, null-pointer tolerance, successful intentional-DNP initialization, and retained bounded failure/recovery of the other sensors. It also verifies unsupported population compile rejection and that the default/explicit legacy driver still compile.
- Existing sensor-bus recovery and optical-quiescence integration checks pass. They cover the unchanged legacy fault/recovery wiring; the new host test provides execution coverage of DNP behavior.
- There is no physical DNP-board test, populated-AS7331 driver test, calibration, flight validation, or flashing in this result.

Reproduce from the repository root:

```sh
python3 analysis/v1_1_release_20261012/as7331/firmware/test_uv_dnp.py
python3 analysis/diagnostics/sensor_i2c_recovery_integration_test.py
python3 analysis/diagnostics/ltr390_quiescence_integration_test.py
/Users/twarn/.platformio/penv/bin/pio run -d firmware -e stratolink_v1_1 -e stratolink_v1_1_uv_dnp
```

The private compiled binaries remain under PlatformIO's ignored build directory and scratch storage; only hashes and test summaries are recorded here.
