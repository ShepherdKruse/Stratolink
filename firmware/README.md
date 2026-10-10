# Stratolink Firmware

Phase 1-4 firmware for the Stratolink balloon PCB: periodic telemetry cycle with power-tier logic, GPS, I2C sensors (TMP117, MS5611, LIS2DH12, LTR-390UV), PDM microphone acoustic event detection, 40-byte observability payload, LoRaWAN uplink via RadioLib + manual protocol (TTN OTAA, runtime multi-region from GPS), tier-based sleep, STOP1 + RTC wake, and burst mode on LIS2DH12 freefall (INT1/PA8) with rapid beacon until freefall clears.

**Full description, approach, and usage:** see [DOCUMENTATION.md](DOCUMENTATION.md).

## Structure

- **include/**: Board and config: `stratolink_pins.h`, `config.h`, `secrets.h` (copy from `secrets.h.example`), `telemetry.h`, `power_adc.h`, `gps_ublox.h`, `lorawan.h`, `sensors.h`, `sensor_tmp117.h`, `sensor_ms5611.h`, `sensor_lis2dh12.h`, `sensor_ltr390.h`, `mic_acoustic.h`.
- **src/**: Implementation:
  - `main.cpp`: Setup and loop: tier → freshness-gated GPS → sensors → primary uplink → optional Class-A command/typed auxiliary uplink → surplus-only LongFast service → STOP1. The CTT stage is compiled out for StratoLink-2's unqualified high-band RF path.
  - `telemetry.cpp`: 40-byte big-endian telemetry-v2 pack (the webhook also accepts historical 35-byte v1).
  - `power_adc.cpp`: VSTOR and solar ADC using VREFINT plus a ~642 us high-impedance HAL sample aperture; power tier from `stratolink_pins.h` thresholds.
  - `gps_ublox.cpp`: u-blox over UART1, airborne <4g, freshness-gated fix (fresh PVT + iTOW); NOGPS on no fresh fix, PA0 reset recovery.
  - `lorawan.cpp`: LoRaWAN OTAA/session/counter persistence, runtime GNSS-authorized region, Class-A command receive, typed event uplinks, Meshtastic relay, authenticated B2B, and the disabled-by-default CTT listener/diagnostic on the shared radio.
  - `sensors.cpp`: I2C init (board pins) and init of TMP117, MS5611, LIS2DH12, LTR-390UV. TMP117 failure non-blocking.
  - `sensor_tmp117.cpp`: TMP117 one-shot temperature (decidegrees, matching the 0.1 °C wire field); falls back to MS5611 baro temp.
  - `sensor_ms5611.cpp`: MS5611 pressure (0.1 hPa) and optional internal temp.
  - `sensor_lis2dh12.cpp`: LIS2DH12 accelerometer X/Y/Z (0.01 m/s²), with 100 Hz low-power freefall INT1 operation.
  - `sensor_ltr390.cpp`: LTR-390UV-01: UV index, ambient lux, and readback-confirmed standby with verified software-reset recovery.
  - `mic_acoustic.cpp`: T3902 PDM mic via SPI1 RXONLY; DC-blocked variance acoustic-event detection with an adaptive noise floor.
  - **Phase 3:** `power_manager.cpp`: watchdog-safe, RTC-debited STOP1 sleep with exact IRQ-state restoration and tier-based intervals. At EMERGENCY/CRITICAL, I2C sensors are skipped.
  - **Phase 4:** LIS2DH12 freefall on INT1 (PA8) wakes MCU from STOP1; `power_manager_attach_freefall_wakeup()` and `power_manager_did_wake_from_freefall()`. Burst mode: short GPS timeout and 10 s sleep until a successful `sensor_lis2dh12_is_freefall_cleared()` measurement; unknown sensor state remains in the six-cycle bounded recovery path. Config: `BURST_GPS_TIMEOUT_MS`, `BURST_SLEEP_SEC`.

## Build

```bash
cd firmware
platformio run
```

Copy `include/secrets.h.example` to `include/secrets.h` and set your LoRaWAN keys for real deployment. In `config.h`, `POWER_SAVE_MODE` enables STOP1 sleep with RTC wake; `SLEEP_INTERVAL_*_SEC` define tier-based intervals.

## Upload

```bash
platformio run --target upload
```

Requires J-Link via SWD (`upload_protocol = jlink` in `platformio.ini`). For flight hardware, follow the guarded post-soak flash/readback procedure in `analysis/diagnostics/STRATOLINK2_POSTSOAK_HIL.md`; do not assume a fixed power-cycle delay proves SubGHz-radio state.

## Payload

40 bytes, big-endian. It retains the first 34 v1 data bytes and adds power/reset/GNSS age, command acknowledgement, relay state, and relay/CTT activity. Full field layout and units are in [DOCUMENTATION.md](DOCUMENTATION.md).
