# Stratolink Firmware

Phase 1–4 firmware for the Stratolink balloon PCB: periodic telemetry cycle with power-tier logic, GPS, I2C sensors (TMP117, MS5611, LIS2DH12, LTR-390UV), PDM microphone acoustic event detection, 35-byte payload, LoRaWAN uplink via RadioLib + manual protocol (US915 sub-band 2 / TTN, OTAA), tier-based sleep, STOP2 + RTC wake, and burst mode on LIS2DH12 freefall (INT1/PA8) with rapid beacon until freefall clears.

**Full description, approach, and usage:** see [DOCUMENTATION.md](DOCUMENTATION.md).

## Structure

- **include/** — Board and config: `stratolink_pins.h`, `config.h`, `secrets.h` (copy from `secrets.h.example`), `telemetry.h`, `power_adc.h`, `gps_ublox.h`, `lorawan.h`, `sensors.h`, `sensor_tmp117.h`, `sensor_ms5611.h`, `sensor_lis2dh12.h`, `sensor_ltr390.h`, `mic_acoustic.h`.
- **src/** — Implementation:
  - `main.cpp` — Setup and loop: power ADC, GPS, LoRaWAN, sensors, mic init; each cycle: tier → GPS fix (if tier allows) → read sensors → fill telemetry → pack → uplink → sleep.
  - `telemetry.cpp` — 35-byte big-endian payload pack (matches webhook parser).
  - `power_adc.cpp` — VSTOR and solar ADC with 50 ms settle; power tier from stratolink_pins.h thresholds.
  - `gps_ublox.cpp` — u-blox over UART1, set airborne <4g, poll for fix.
  - `lorawan.cpp` — LoRaWAN (RadioLib radio + manual protocol): OTAA join, US915 sub-band 2 for TTN, unconfirmed uplink. Software AES-128-CMAC.
  - `sensors.cpp` — I2C init (board pins) and init of TMP117, MS5611, LIS2DH12, LTR-390UV. TMP117 failure non-blocking.
  - `sensor_tmp117.cpp` — TMP117 one-shot temperature (centidegrees); falls back to MS5611 baro temp.
  - `sensor_ms5611.cpp` — MS5611 pressure (0.1 hPa) and optional internal temp.
  - `sensor_lis2dh12.cpp` — LIS2DH12 accelerometer X/Y/Z (0.01 m/s²), 1 Hz low-power.
  - `sensor_ltr390.cpp` — LTR-390UV-01: UV index and ambient lux.
  - `mic_acoustic.cpp` — T3902 PDM mic via SPI1 RXONLY; RMS energy acoustic event detection.
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

Requires J-Link via SWD (upload_protocol = jlink in platformio.ini). After flashing, a 30-second power cycle is required to fully reset the SubGHz radio.

## Payload

35 bytes, big-endian. Full field layout and units are in [DOCUMENTATION.md](DOCUMENTATION.md).
