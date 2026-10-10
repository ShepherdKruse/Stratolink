# Stratolink Firmware Documentation

This document describes the balloon payload firmware: its approach, behavior, and how to build and use it.

## 1. Approach

The firmware is designed for a supercap-powered PCB that runs a periodic telemetry cycle and must survive long dark periods. The design is phased and power-aware.

1. **Single cycle.** Each period: wake (from RTC or freefall interrupt), read power tier from VSTOR/solar ADC, optionally get a GPS fix, read I2C sensors, pack a 40-byte payload, send one LoRaWAN uplink, then sleep until the next interval.

2. **Power tiers.** VSTOR voltage selects a tier (FULL, REDUCED, NO_GPS, EMERGENCY, CRITICAL). GPS is attempted only in FULL and REDUCED; I2C sensors are skipped in EMERGENCY/CRITICAL (LoRa beacon only). All normal tiers retain the 1200 s primary cadence; lower tiers preserve energy by gating expensive work rather than scheduling a sleep longer than the GNSS-backed RF-region lease.

3. **STOP1 sleep.** When `POWER_SAVE_MODE` is enabled, the MCU enters STOP1 (LP regulator on) and wakes on an RTC alarm via the internal wake-up line (`PWR.CR3.EIWUL`). Every normal tier uses 1200 s; burst sleep uses 10 s. The final pre-supercap profile measured a 6.730 µA median STOP1 phase, and the exact v15 flight image measured 6.688 µA over its five terminal 5 s bins at 4,660 mV. The two medians differ by 0.042 µA and every selected bin is below 10 µA. Those measurements apply only to the historical room-temperature board and image before the energy store was fitted. They do not qualify this revision, the final supercapacitor assembly, or cold endurance. STOP2 was dropped on this RAK3172 module because bench runs reset on its regulator-off transition.

4. **Burst mode.** The LIS2DH12 accelerometer drives INT1 (PA8) when a freefall condition is detected. PA8 is used as an EXTI wake source so the MCU can wake from STOP1 on burst. After a freefall wake, the firmware runs a rapid-beacon loop (shorter GPS timeout, 10 s sleep) until the acceleration returns above a threshold (~0.5g), then reverts to normal tier-based behavior.

5. **Independent watchdog (IWDG).**  32.7 s timeout from LSI, refreshed at the top of `loop()` and between major operations (after GPS, after sensor reads, after TX-pack, on every wake).  Keeps running in STOP1 (FLASH `IWDG_STOP` option bit = 1 by default), so multi-minute sleeps are chunked below the 32 s timeout with an IWDG refresh between chunks to avoid a false reset.  Recovers from any run-mode hang within ~33 s.

6. **Payload contract.** One 40-byte big-endian telemetry-v3 primary uplink per successful cycle, aligned with the ground-station webhook. The first 34 data bytes retain v1, while the last six bytes expose acoustic/power/reset state, boot count modulo 256, GNSS fix age, authenticated-server proof/miss/recovery state, command ACK/relay state, and saturated relay/CTT activity. The parser accepts exact 35-byte v1 and both legacy/current 40-byte v2/v3 frames, and treats raw LoRaWAN bytes as authoritative over formatter JSON. Sparse CTT and B2B records use dedicated fPorts 11 and 12 under one shared auxiliary-uplink budget. No raw audio or high-rate streams.

## 2. What the Firmware Does

### 2.1 Normal cycle

1. Wake (RTC or EXTI).
2. If wake was from INT1 (freefall), set burst mode.
3. Read VSTOR and solar ADC using the calibrated VREFINT path and the ~642 us high-impedance ADC sample aperture; derive power tier.
4. If tier allows GPS (or burst mode), attempt a fix on UART1 (u-blox MAX-M10S). AIRBORNE_4G must be verified before accepting PVT; the bounded startup path reads first and writes only if needed. A fix requires `fixOK`, at least four satellites, physically bounded fields, and two forward-moving, valid-date/time PVT epochs; otherwise the wire GPS fields remain zero.
5. If tier allows I2C sensors, read TMP117 (temperature, with MS5611 baro temp fallback), MS5611 (pressure), LIS2DH12 (accel), LTR-390UV (UV index, ambient lux), and T3902 mic (acoustic event detection). Environmental fields start each cycle at explicit unavailable sentinels and are overwritten only by successful reads; power-gated or failed channels therefore decode as null rather than plausible zero-valued science. Every attempted LTR390 enable must end in exact standby readback or a verified software reset. A still-unconfirmed optical state closes auxiliary radios and gets five bounded 60 s bus/quiescence-only retries. If it persists, normal primary GPS/TTN cadence resumes in degraded mode while optical reads and all auxiliary services remain disabled; a non-critical light sensor can never silence tracking indefinitely.
6. Fill telemetry structure (GPS, power, sensors, UV, acoustic and diagnostic state), pack 40 bytes.
7. If the current rail, unexpired regional authority, and session allow TX, send one fPort-1 uplink with a frame counter reserved durably before RF. Most primaries are unconfirmed. An unproven session gets one prompt eligible `ConfirmedDataUp` probe, followed by a 24-qualified-primary interval. Any authenticated data downlink is server proof. Three qualified probes that each transmit locally and complete both healthy Class-A windows without authenticated evidence retire the session and force same-region OTAA recovery. Fresh advancing PVT, legal GNSS authority, a REDUCED-or-better Class-A rail, and no burst/freefall are mandatory; local TX/RX/PHY faults and power or mission preemption abandon the probe without a miss. Regional authority normally comes from fresh GNSS. A create-once pre-launch action may instead place an exact plan plus `LAUNCH` source in retained TAMP state so the first join and primary health packets do not depend on an immediate fix, but launch authority never advances the liveness policy.
8. When command receive is enabled or a confirmed probe is due, open the network-assigned Class-A RX1/RX2 windows and dispatch authenticated fPort-10 commands. A third qualified miss immediately invalidates the RAM session and suppresses every later same-cycle TTN/CTT/Meshtastic/B2B RF path. Recovery clears only the retained session marker, republishes the same fresh GNSS plan with the actual current-cycle fix age, and waits until a later cycle to rejoin. If either durable step fails, RAM authority is revoked and the board stays RF-quiet. This deliberately prefers recovery from a stale Network Server session over continued one-way telemetry: a persistent downlink-only outage can also prevent the required JoinAccept and leave the board quiet until downlink returns. At most one queued CTT/B2B auxiliary uplink is attempted every eight successful primary cycles.
9. If in burst mode, check whether freefall is cleared (accel magnitude &gt; ~0.5g); otherwise enforce the six-cycle runaway cap and cooldown.
10. Choose the sleep budget: burst 10 s; otherwise every normal tier uses 1200 s. At the minimum specified LSI frequency this is conservatively charged as 1302 s, leaving a complete 300 s active-work margin strictly inside the 1800 s GNSS-backed region lease.
11. Only after a healthy primary exchange, with authenticated server proof, confirmed GNSS-derived authority, confirmed GNSS standby, a FULL rail, a current legal region, and active solar, enter the 60 s experimental CTT listener and then the shared LongFast Meshtastic/B2B window. Launch authority permits only OTAA, primary fPort-1 health, and its Class-A control exchange; auxiliary fPorts 11/12 and shared-radio service windows wait for fresh GNSS. Both windows self-abort at the VSTOR floor and restore the full LoRaWAN PHY. The fitted high-band RAK3172-9 has no manufacturer-qualified 434 MHz receive path, so CTT protocol/HIL success does not establish airborne sensitivity or range.
12. Put the SX1262 into retained sleep and enter watchdog-chunked STOP1 for the remaining budget. An unready PHY or failed first sleep gets one bounded full radio reinitialization and must then confirm sleep, otherwise the MCU resets before the long idle interval. INT1 (PA8) remains an alternate wake source.

### 2.2 Burst mode (Phase 4)

- Entered when the MCU wakes from PA8 (LIS2DH12 INT1 freefall).
- GPS timeout is reduced (e.g. 10 s).
- Sleep between cycles is short (e.g. 10 s).
- Burst mode is cleared only when `sensor_lis2dh12_is_freefall_cleared()` has a successful magnitude-above-threshold sample. An unavailable sample stays in recovery until the bounded six-cycle cap.
- Same 40-byte payload and same LoRa path; only timing and GPS timeout change.

### 2.3 Hardware assumptions

- **Board.** Pinout and thresholds are in `include/stratolink_pins.h` (GPS UART, I2C pins and addresses, ADC pins/sample aperture, PA8 for INT1, power-tier voltages).
- **GPS.** u-blox MAX-M10S on UART1; airborne dynamic model 8 must be set after power-on.
- **I2C.** TMP117 (0x48, with MS5611 baro temp fallback), MS5611 (0x76), LIS2DH12 (0x18), LTR-390UV (0x53) on a single bus. LIS2DH12 runs at 100 Hz when freefall INT1 is enabled.
- **Microphone.** T3902 PDM mic via SPI1 RXONLY (PB3=SCK, PB4=MISO, 3 MHz). Streaming DC-blocked variance detection with an adaptive noise floor; this is a broadband anomaly flag, not a source classifier.
- **Power.** VSTOR and solar use the STM32 factory VREFINT calibration and a 160.5-cycle sample at a 250 kHz ADC clock. Before every STOP1 interval, the firmware disables the ADC, VREFINT path, internal ADC regulator, and ADC run/sleep bus clocks, verifies `ADEN`, `ADVREGEN`, and `VREFEN` are clear, and resets rather than entering long sleep if a bounded peripheral-reset fallback cannot prove quiescence. Tier thresholds and sleep intervals are configurable.

## 3. How to Use It

### 3.1 Build

1. Install PlatformIO (CLI or IDE).
2. From the repo root: `cd firmware` then `platformio run`.
3. Dependencies are in `platformio.ini` (SparkFun u-blox GNSS, STM32LowPower, RadioLib). Include path `-I include` is set.

### 3.2 Secrets and config

1. Copy `include/secrets.h.example` to `include/secrets.h`. Do not commit `secrets.h`.
2. In `secrets.h`, set LoRaWAN keys (DEV_EUI, APP_EUI, APP_KEY) for your TTN application.
3. In `include/config.h` you can adjust:
   - `POWER_SAVE_MODE`, enable STOP1 + RTC (and EXTI) wake.
   - `TRANSMIT_INTERVAL_SEC`, default interval when not using tier-based sleep.
   - `SLEEP_INTERVAL_*_SEC`, per-tier sleep intervals (FULL, REDUCED, NO_GPS, EMERGENCY).
   - `BURST_GPS_TIMEOUT_MS`, `BURST_SLEEP_SEC`, burst-mode GPS timeout and sleep.
   - `DEBUG_ENABLE`, `DEBUG_SERIAL_BAUD`, debug print over serial.
   - `GNSS_ENABLE`, enable/disable GPS (and stub it in the driver).

### 3.3 Upload

- `platformio run --target upload` uses J-Link via SWD (see `platformio.ini`). On flight hardware, use the guarded post-soak flash/readback sequence in `analysis/diagnostics/STRATOLINK2_POSTSOAK_HIL.md`; a fixed delay alone is not evidence that the SubGHz radio restored correctly.

### 3.4 Ground station

- Configure the TTN webhook with the same dedicated Bearer secret as the server and point it at the ground-station API (e.g. `https://your-domain.com/api/ttn-webhook`).
- Route fPort 1 as exact 35-byte telemetry v1 or 40-byte telemetry v2/v3, fPort 11 as CTT event v2, and fPort 12 as B2B wire v3. Apply all database migrations through `20260831043000_telemetry_server_liveness_v3.sql` before flashing telemetry v3.

## 4. Architecture and Modules

| Module | Role |
|--------|------|
| `main.cpp` | Setup (ADC, GPS, LoRaWAN, sensors, freefall INT1, power manager). Loop: tier, GPS, sensors, pack, TX, burst clear, sleep. |
| `telemetry.cpp` | Packs a `telemetry_input_t` into 40 big-endian telemetry-v3 bytes while preserving the v1 prefix and v2 decoder compatibility. |
| `power_adc.cpp` | VSTOR/solar ADC with VREFINT validation and a long HAL sample aperture; tier/load/sleep policy. |
| `gps_ublox.cpp` | UART1 init, DYNMODEL 8, freshness-gated get-fix (fresh PVT + advancing iTOW, fix-OK, SIV>=4); NOGPS on no fresh fix; explicit confirmed-standby/reset-held/uncontained results; terminal PMREQ failure holds PA0 RESET_N low and recovery releases it only at the conservative cold-reset rail floor. RESET-held current still requires exact-assembly qualification. |
| `lorawan.cpp` | Multi-region LoRaWAN, durable counters/session, Class-A commands, typed auxiliary uplinks, shared-radio CTT, Meshtastic, and authenticated B2B. |
| `ctt_decode.cpp`, `ctt_queue.cpp`, `ctt_event.cpp` | Experimental CTT 434 MHz frame validation, bounded transactional queue, and fPort-11 event v2 packing. The fitted high-band RAK3172 does not officially support 434 MHz; enabled software and close-range HIL are not evidence of usable airborne tag sensitivity. |
| `b2b.cpp` | Wire-v3 AES-CMAC framing, dedup/TTL, bounded store-and-forward queues, age renewal, and airtime accounting. |
| `meshtastic_relay_mac.cpp` | Opaque LongFast header validation, ROUTER_LATE contention, duplicate cancellation, and bounded pending queue. |
| `command.cpp` | Durable-sequence Stage-1 PING and retained public-Meshtastic relay toggle. The next primary uplink carries the last applied sequence and actual relay state. |
| `sensors.cpp` | I2C init (board pins on STM32), then init TMP117, MS5611, LIS2DH12, LTR-390UV. TMP117 failure is non-blocking. |
| `sensor_tmp117.cpp` | One-shot temperature read; result in decidegrees (0.1 °C), exactly matching the wire field. Falls back to MS5611 baro temp when TMP117 unavailable. |
| `sensor_ms5611.cpp` | PROM read, D1/D2 conversion; pressure in 0.1 hPa; optional internal temp in centidegrees. |
| `sensor_lis2dh12.cpp` | Accel read (0.01 m/s²); freefall INT1 enable (100 Hz, threshold/duration from board.h); INT1_SRC clear; freefall-cleared check (magnitude &gt; ~0.5g). |
| `sensor_ltr390.cpp` | LTR-390UV-01: UV index (0-15+), ambient light (lux), and readback-confirmed standby with software-reset recovery. |
| `mic_acoustic.cpp` | T3902 PDM mic via SPI1 RXONLY at 3 MHz. Streaming DC-blocked variance detection with an adaptive noise floor for a broadband anomaly flag. |
| `power_manager.cpp` | Early IWDG/RTC init, 28 s STOP1 chunks, actual elapsed-time debit, exact UART IRQ restoration, freefall wake/chatter policy, and retained TAMP records. |

Headers in `include/` define the APIs and `stratolink_pins.h` holds hardware constants (pins, addresses, thresholds, settle time).

## 5. Payload Format (40-byte v3, big-endian)

| Bytes | Field | Type | Units / encoding |
|-------|--------|------|-------------------|
| 0-3 | Latitude | int32 | degrees × 1e7 |
| 4-7 | Longitude | int32 | degrees × 1e7 |
| 8-11 | Altitude | int32 | meters |
| 12-13 | Temperature | int16 | 0.1 °C; `-32768` means unavailable |
| 14-15 | Pressure | uint16 | 0.1 hPa; `0xFFFE` means unavailable |
| 16-17 | Solar voltage | uint16 | mV |
| 18-19 | Battery (VSTOR) | uint16 | mV |
| 20-21 | GPS speed | uint16 | 0.01 m/s |
| 22-23 | GPS heading | uint16 | 0.01 ° |
| 24 | GPS satellites | uint8 | count |
| 25-26 | Accel X | int16 | 0.01 m/s²; all three axes use `-32768` when the atomic sample is unavailable |
| 27-28 | Accel Y | int16 | 0.01 m/s²; same atomic sentinel contract |
| 29-30 | Accel Z | int16 | 0.01 m/s²; same atomic sentinel contract |
| 31 | UV index | uint8 | integer UVI; `0xFE` unavailable, `0xFF` genuine high/saturated reading |
| 32-33 | Ambient lux | uint16 | lux; `0xFFFE` unavailable, `0xFFFF` genuine saturation |
| 34 bits 0-3 | Acoustic/power code | uint4 | 0-9 = `power tier * 2 + event` (event 0 quiet, 1 above adaptive threshold); 10-14 = microphone unavailable at power tier 0-4; 15 invalid |
| 34 bits 4-6 | Reset cause | uint3 | 0 unknown, 1 watchdog, 2 software, 3 low-power/option, 4 cold power-on, 5 warm brownout, 6 NRST |
| 34 bit 7 | Command ACK valid | bit | byte 38 contains a durably applied sequence |
| 35 | Boot count | uint8 | retained boot counter low byte; wraps modulo 256 |
| 36-37 bit 15 | Telemetry-v3 marker | bit | always 1 in newly emitted frames |
| 36-37 bits 12-14 | Authenticated server proof | uint3 | accepted authenticated data downlinks, modulo 8 |
| 36-37 bits 10-11 | Qualified miss streak | uint2 | consecutive fully qualified confirmed probes with no authenticated response, 0-3 |
| 36-37 bit 9 | Session-recovery parity | bit | completed same-region recovery count modulo 2 |
| 36-37 bits 0-8 | Fresh GNSS fix age | uint9 | minutes since a fix accepted this boot, saturated at 510; 511 means none this boot |
| 38 | Command ACK sequence | uint8 | meaningful only when byte 34 bit 7 is set |
| 39 bit 7 | Public relay enabled | bit | retained actual public-Meshtastic policy |
| 39 bits 4-6 | Relay forward delta | uint3 | since last successful primary, saturates at 7 |
| 39 bits 0-3 | CTT tag delta | uint4 | since last successful primary, saturates at 15 |

The ground station decodes this layout directly from `frm_payload`. Historical exact-length 35-byte v1 frames remain accepted. A 40-byte word at bytes 36-37 with bit 15 clear is legacy telemetry v2 and retains fix ages 0..`0x7FFF`; exact legacy `0xFFFF` still means no fix. The v3 marker intentionally repurposes theoretical legacy ages `0x8000`..`0xFFFE`. Those ages require at least 22.76 days without a fix, while the GNSS-derived regional authority suppresses legal primary TX after 30 minutes, and telemetry v2 was never frozen or flashed. Other marked words are v3. New firmware never emits `0xFFFF`: the sole all-ones v3 combination canonicalizes proof residue 7 to 6 while preserving the safety-relevant miss, recovery, and no-fix facts. All other primary lengths fail closed. Firmware initializes each cycle with unavailable environmental sentinels and an unavailable microphone code; successful drivers overwrite only their own fields. An I2C failure therefore cannot masquerade as 0 °C, zero-g, or darkness, and a skipped or failed microphone capture cannot masquerade as quiet. Existing valid telemetry-v2 acoustic/power codes 0-9 are unchanged. Exact-image diagnostic counters remain required to distinguish capture failure from a power-policy skip and to validate detector behavior in HIL.

## 6. Configuration Summary

| Symbol | Default | Meaning |
|--------|---------|---------|
| `POWER_SAVE_MODE` | true | Use STOP1 + RTC (and EXTI) wake instead of delay. |
| `SLEEP_INTERVAL_FULL_SEC` | 1200 | Full-tier cycle budget. |
| `SLEEP_INTERVAL_REDUCED_SEC` | 1200 | Reduced-tier cycle budget. |
| `SLEEP_INTERVAL_NO_GPS_SEC` | 1200 | GPS-skipped cycle budget. |
| `SLEEP_INTERVAL_EMERGENCY_SEC` | 1200 | Emergency/critical cycle budget. |
| `BURST_GPS_TIMEOUT_MS` | 10000 | Max GPS wait in burst mode (ms). |
| `BURST_SLEEP_SEC` | 10 | Sleep between cycles in burst mode (s). |
| `SENSOR_QUIESCE_RETRY_SLEEP_MS` | 60000 | Quiet retry interval after unresolved LTR390 standby (ms). |

Tier thresholds (voltage) are in `stratolink_pins.h` (e.g. `POWER_TIER_FULL_V`, `POWER_TIER_NO_GPS_V`).

## 7. Extending the Firmware

- **Multi-region LoRaWAN (implemented in software; exact-SKU RF qualification incomplete).** Region is auto-selected at runtime from the GPS fix (`region_manager.cpp`); Flight 3 switched US915 to EU868 and produced 142 received EU868 uplinks. The production BOM, however, resolves to `RAK3172-9-SM-NI`, whose RAK ordering entry covers 9xx MHz US915/AU915/KR920/AS923; RAK assigns EU868 to the separate `-8` SKU. Historical reception is useful operating evidence but does not establish specified conducted power/sensitivity, matching, certification, cold margin, or assembly repeatability at 868 MHz. Duty-cycle enforcement for EU868/AS923 is not implemented in firmware; the 20-minute flight cadence is modeled below the relevant limit, but exact-image regulatory airtime remains a release check.
- **Session and regional-authority persistence (implemented).** The OTAA session, next uplink/downlink counters, network-assigned RX delay, regional-authority age/source/exact plan, command sequence plus relay state, and next B2B ID use corruption-detecting retained records. BKP18 uses a versioned magic and CRC-8 to distinguish `GNSS` from explicit `LAUNCH` authority and bind either to US915/EU868/AS923/AU915 without consuming another TAMP word; legacy age-only records migrate only when a separately CRC-protected retained session supplies the same exact plan. Session commits read back every word and CRC; any mismatch makes three bounded, verified attempts to invalidate both session and regional-authority publish markers. A save is permitted only when RAM provenance and the active radio plan agree, so missing/corrupt state cannot self-renew from zero or authorize a mismatched session. Warm reset/STOP preserve valid state. True backup-domain loss never recreates launch authority from a compile-time default: it forces RF quiet until fresh GNSS or another explicit pre-launch provisioning action. Generated HIL no longer emits the former partial-RAM authorization script; the sole launch mutation path is the create-once BKP18 provisioner with full TAMP before/after evidence. `BENCH_SEED_REGION` is separately constrained to US915 and imports only a retained US915 session.
- **Server-liveness observability reset semantics.** The current miss streak, countdown, and probe-pending intent are packed into the high bits of the CRC-protected session `rxDelaySec` word; interrupted pending intent imports as ambiguity, while a retained third miss remains recovery-due across reset. The telemetry proof-modulo and recovery-parity counters are intentionally RAM diagnostics and reset to zero on MCU reset. A reset between session invalidation and the next primary can therefore erase the parity edge. Remote soak evidence disambiguates that accepted limitation with the retained boot count/reset cause plus TTN `confirmed`, `session_key_id`, frame counter, correlation IDs, and the next packet's liveness state. Successful OTAA recovery changes `session_key_id`; an ordinary MCU reset retaining the session does not.
- **Acoustic classifier.** Current mic driver uses simple RMS energy detection (event flag only, no audio is captured or transmitted). Future: replace with CNN-based spectrogram classifier for aircraft/rocket/drone identification. CMSIS-DSP FFT + TinyML inference on Cortex-M4.
- **Downlink commands.** Stage 1 receives authenticated Class-A fPort-10 commands and implements PING plus a public-Meshtastic relay toggle with durable replay sequencing and relay-state persistence. Telemetry v2/v3 reports the last durably applied sequence and actual relay state on the next successful primary. Cadence/SF/GPS reset/safe mode/rejoin/data dump, dead-man reversion, and commit-confirm behavior changes remain design-only and must not be assumed available in flight.
