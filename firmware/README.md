# Stratolink Firmware

Phase 1–4 firmware for the Stratolink balloon PCB: periodic telemetry cycle with power-tier logic, GPS, I2C sensors, 38-byte payload, LoRaWAN uplink stub, tier-based sleep, STOP2 + RTC wake, and burst mode on LIS2DH12 freefall (INT1/PA8) with rapid beacon until freefall clears.

**Full description, approach, and usage:** see [DOCUMENTATION.md](DOCUMENTATION.md).

## Structure

- **include/** — Board and config: `board.h`, `config.h`, `secrets.h` (copy from `secrets.h.example`), `telemetry.h`, `power_adc.h`, `gps_ublox.h`, `lorawan.h`, `sensors.h`, `sensor_tmp117.h`, `sensor_ms5611.h`, `sensor_lis2dh12.h`.
- **src/** — Implementation:
  - `main.cpp` — Setup and loop: power ADC, GPS, LoRaWAN, sensors init; each cycle: tier → GPS fix (if tier allows) → read TMP117/MS5611/LIS2DH12 → fill telemetry → pack → uplink → delay.
  - `telemetry.cpp` — 38-byte big-endian payload pack (matches webhook parser).
  - `power_adc.cpp` — VSTOR and solar ADC with 50 ms settle; power tier from board.h thresholds.
  - `gps_ublox.cpp` — u-blox over UART1, set airborne <4g, poll for fix.
  - `lorawan.cpp` — Stub (logs only). Replace with STM32LoRaWAN or AT driver for real TX.
  - `sensors.cpp` — I2C init (board pins) and init of TMP117, MS5611, LIS2DH12.
  - `sensor_tmp117.cpp` — TMP117 one-shot temperature (centidegrees).
  - `sensor_ms5611.cpp` — MS5611 pressure (0.1 hPa) and optional internal temp.
  - `sensor_lis2dh12.cpp` — LIS2DH12 accelerometer X/Y/Z (0.01 m/s²), 1 Hz low-power.
  - **Phase 3:** `power_manager.cpp` — STOP2 sleep with RTC wake when `POWER_SAVE_MODE` is true; tier-based sleep intervals. At EMERGENCY/CRITICAL, I2C sensors are skipped.
  - **Phase 4:** LIS2DH12 freefall on INT1 (PA8) wakes MCU from STOP2; `power_manager_attach_freefall_wakeup()` and `power_manager_did_wake_from_freefall()`. Burst mode: short GPS timeout and 10 s sleep until `sensor_lis2dh12_is_freefall_cleared()`. Config: `BURST_GPS_TIMEOUT_MS`, `BURST_SLEEP_SEC`.

## Build

```bash
cd firmware
platformio run
```

Copy `include/secrets.h.example` to `include/secrets.h` and set your LoRaWAN keys for real deployment. In `config.h`, `POWER_SAVE_MODE` enables STOP2 sleep with RTC wake; `SLEEP_INTERVAL_*_SEC` define tier-based intervals.

## Upload

```bash
platformio run --target upload
```

Requires ST-Link or compatible debugger (upload_protocol = stlink in platformio.ini).

## Payload

38 bytes, big-endian. Full field layout and units are in [DOCUMENTATION.md](DOCUMENTATION.md).
