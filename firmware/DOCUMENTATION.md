# Stratolink Firmware Documentation

This document describes the balloon payload firmware: its approach, behavior, and how to build and use it.

## 1. Approach

The firmware is designed for a supercap-powered PCB that runs a periodic telemetry cycle and must survive long dark periods. The design is phased and power-aware.

1. **Single cycle.** Each period: wake (from RTC or freefall interrupt), read power tier from VSTOR/solar ADC, optionally get a GPS fix, read I2C sensors, pack a 38-byte payload, send one LoRaWAN uplink, then sleep until the next interval.

2. **Power tiers.** VSTOR voltage selects a tier (FULL, REDUCED, NO_GPS, EMERGENCY, CRITICAL). Lower tiers reduce load: no GPS below NO_GPS, no I2C sensors in EMERGENCY/CRITICAL (LoRa beacon only), and longer sleep intervals to preserve energy.

3. **STOP2 sleep.** When `POWER_SAVE_MODE` is enabled, the MCU enters STOP2 (deep sleep) and wakes on an RTC alarm. Sleep duration is tier-based. This minimizes current between cycles.

4. **Burst mode.** The LIS2DH12 accelerometer drives INT1 (PA8) when a freefall condition is detected. PA8 is used as an EXTI wake source so the MCU can wake from STOP2 on burst. After a freefall wake, the firmware runs a rapid-beacon loop (shorter GPS timeout, 10 s sleep) until the acceleration returns above a threshold (~0.5g), then reverts to normal tier-based behavior.

5. **Payload contract.** One 38-byte big-endian uplink per cycle, aligned with the ground-station webhook and TTN payload formatter. No raw audio or high-rate streams; optional acoustic-event byte reserved for future mic/FFT use.

## 2. What the Firmware Does

### 2.1 Normal cycle

1. Wake (RTC or EXTI).
2. If wake was from INT1 (freefall), set burst mode.
3. Read VSTOR and solar ADC (50 ms settle per board requirement), derive power tier.
4. If tier allows GPS (or burst mode), attempt a fix on UART1 (u-blox MAX-M10S); DYNMODEL 8 (airborne &lt;4g) is applied at init so fixes work above 12 km.
5. If tier allows I2C sensors, read TMP117 (temperature), MS5611 (pressure), LIS2DH12 (accel); otherwise leave those fields zero.
6. Fill telemetry structure (GPS, power, sensors, reserved gyro/acoustic), pack 38 bytes.
7. If tier allows TX, send one unconfirmed uplink.
8. If in burst mode, check whether freefall is cleared (accel magnitude &gt; ~0.5g); if so, clear burst mode.
9. Choose sleep duration: burst mode 10 s, else tier-based (e.g. FULL 60 s, REDUCED 120 s, NO_GPS 300 s, EMERGENCY 120 s).
10. Enter sleep (STOP2 with RTC wake, or delay if power save disabled). INT1 (PA8) remains an alternate wake source.

### 2.2 Burst mode (Phase 4)

- Entered when the MCU wakes from PA8 (LIS2DH12 INT1 freefall).
- GPS timeout is reduced (e.g. 10 s).
- Sleep between cycles is short (e.g. 10 s).
- Burst mode is cleared when `sensor_lis2dh12_is_freefall_cleared()` is true (magnitude above threshold).
- Same 38-byte payload and same LoRa path; only timing and GPS timeout change.

### 2.3 Hardware assumptions

- **Board.** Pinout and thresholds are in `include/board.h` (GPS UART, I2C pins and addresses, ADC pins and settle time, PA8 for INT1, power-tier voltages).
- **GPS.** u-blox MAX-M10S on UART1; airborne dynamic model 8 must be set after power-on.
- **I2C.** TMP117 (0x48), MS5611 (0x77), LIS2DH12 (0x18) on a single bus. LIS2DH12 runs at 100 Hz when freefall INT1 is enabled.
- **Power.** VSTOR and solar read via ADC with 50 ms settle; tier thresholds and sleep intervals are configurable.

## 3. How to Use It

### 3.1 Build

1. Install PlatformIO (CLI or IDE).
2. From the repo root: `cd firmware` then `platformio run`.
3. Dependencies are in `platformio.ini` (SparkFun u-blox GNSS, STM32LowPower). Include path `-I include` is set.

### 3.2 Secrets and config

1. Copy `include/secrets.h.example` to `include/secrets.h`. Do not commit `secrets.h`.
2. In `secrets.h`, set LoRaWAN keys (DEV_EUI, APP_EUI, APP_KEY) for your TTN application.
3. In `include/config.h` you can adjust:
   - `POWER_SAVE_MODE` — enable STOP2 + RTC (and EXTI) wake.
   - `TRANSMIT_INTERVAL_SEC` — default interval when not using tier-based sleep.
   - `SLEEP_INTERVAL_*_SEC` — per-tier sleep intervals (FULL, REDUCED, NO_GPS, EMERGENCY).
   - `BURST_GPS_TIMEOUT_MS`, `BURST_SLEEP_SEC` — burst-mode GPS timeout and sleep.
   - `DEBUG_ENABLE`, `DEBUG_SERIAL_BAUD` — debug print over serial.
   - `GNSS_ENABLE` — enable/disable GPS (and stub it in the driver).

### 3.3 Upload

- `platformio run --target upload`. Uses ST-Link (see `platformio.ini`). Ensure the board is connected and the correct port/interface is selected.

### 3.4 Ground station

- Configure the TTN webhook to point at your ground-station API (e.g. `https://your-domain.com/api/ttn-webhook`).
- Use the same 38-byte payload format (or the matching TTN Payload Formatter) so the webhook and database receive the expected fields.

## 4. Architecture and Modules

| Module | Role |
|--------|------|
| `main.cpp` | Setup (ADC, GPS, LoRaWAN, sensors, freefall INT1, power manager). Loop: tier, GPS, sensors, pack, TX, burst clear, sleep. |
| `telemetry.cpp` | Single function: pack a `telemetry_input_t` into 38 big-endian bytes. |
| `power_adc.cpp` | VSTOR/solar ADC with 50 ms settle; tier from voltage; `power_adc_get_sleep_interval_sec(tier)`, `power_adc_should_read_sensors()`, `power_adc_can_use_gps()`, `power_adc_can_tx()`. |
| `gps_ublox.cpp` | UART1 init, DYNMODEL 8, blocking get-fix with timeout; last-fix cache. |
| `lorawan.cpp` | Stub: init/join/send log only. Replace with real stack (e.g. STM32LoRaWAN) for production. |
| `sensors.cpp` | I2C init (board pins on STM32), then init TMP117, MS5611, LIS2DH12. |
| `sensor_tmp117.cpp` | One-shot temperature read; result in centidegrees (0.1 °C). |
| `sensor_ms5611.cpp` | PROM read, D1/D2 conversion; pressure in 0.1 hPa. |
| `sensor_lis2dh12.cpp` | Accel read (0.01 m/s²); freefall INT1 enable (100 Hz, threshold/duration from board.h); INT1_SRC clear; freefall-cleared check (magnitude &gt; ~0.5g). |
| `power_manager.cpp` | Init STM32LowPower; sleep via `LowPower.deepSleep(ms)` or `delay(ms)`; attach PA8 EXTI for freefall wake; `power_manager_did_wake_from_freefall()`. |

Headers in `include/` define the APIs and `board.h` holds hardware constants (pins, addresses, thresholds, settle time).

## 5. Payload Format (38 bytes, big-endian)

| Bytes | Field | Type | Units / encoding |
|-------|--------|------|-------------------|
| 0–3 | Latitude | int32 | degrees × 1e7 |
| 4–7 | Longitude | int32 | degrees × 1e7 |
| 8–11 | Altitude | int32 | meters |
| 12–13 | Temperature | int16 | 0.1 °C |
| 14–15 | Pressure | uint16 | 0.1 hPa |
| 16–17 | Solar voltage | uint16 | mV |
| 18–19 | Battery (VSTOR) | uint16 | mV |
| 20–21 | GPS speed | uint16 | 0.01 m/s |
| 22–23 | GPS heading | uint16 | 0.01 ° |
| 24 | GPS satellites | uint8 | count |
| 25–26 | Accel X | int16 | 0.01 m/s² |
| 27–28 | Accel Y | int16 | 0.01 m/s² |
| 29–30 | Accel Z | int16 | 0.01 m/s² |
| 31–36 | Gyro X/Y/Z | int16 | 0.01 °/s (reserved 0) |
| 37 | Acoustic event | uint8 | 0 = no event; non-zero = spectral change (reserved) |

The ground station and TTN Payload Formatter should use this layout for decoding and storage.

## 6. Configuration Summary

| Symbol | Default | Meaning |
|--------|---------|---------|
| `POWER_SAVE_MODE` | true | Use STOP2 + RTC (and EXTI) wake instead of delay. |
| `SLEEP_INTERVAL_FULL_SEC` | 60 | Sleep when VSTOR ≥ FULL threshold. |
| `SLEEP_INTERVAL_REDUCED_SEC` | 120 | Sleep when in REDUCED tier. |
| `SLEEP_INTERVAL_NO_GPS_SEC` | 300 | Sleep when GPS is skipped (NO_GPS tier). |
| `SLEEP_INTERVAL_EMERGENCY_SEC` | 120 | Sleep in EMERGENCY/CRITICAL (beacon only). |
| `BURST_GPS_TIMEOUT_MS` | 10000 | Max GPS wait in burst mode (ms). |
| `BURST_SLEEP_SEC` | 10 | Sleep between cycles in burst mode (s). |

Tier thresholds (voltage) are in `board.h` (e.g. `POWER_TIER_FULL_V`, `POWER_TIER_NO_GPS_V`).

## 7. Extending the Firmware

- **LoRaWAN.** Replace the stub in `lorawan.cpp` with a real stack (e.g. STM32LoRaWAN) and wire region and keys from `config.h`/`secrets.h`.
- **Microphone and FFT (Phase 5).** Add T3902 PDM capture, PDM-to-PCM, 256-point FFT, and baseline comparison; set byte 37 (acoustic_event) when the change metric exceeds a threshold.
- **Downlink.** The current cycle is uplink-only; add downlink handling in the LoRaWAN layer if you need commands or configuration from the ground station.
