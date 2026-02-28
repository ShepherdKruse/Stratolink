#ifndef BOARD_H
#define BOARD_H

#include <Arduino.h>

// =============================================================================
//    GPS — u-blox MAX-M10S (U3)
// =============================================================================
//
// CRITICAL: Must send UBX-CFG-NAVSPG-DYNMODEL = 8 (Airborne <4g) after every
// power-on. Without this, the GPS locks out above 12km due to COCOM limits.
// Non-negotiable for stratospheric flight.
//
// V_BCKP is tied to VCC (3.3V). This keeps the RTC and almanac/ephemeris
// alive through power cycles. Hot-start fixes (~5s) instead of cold-start
// (~30s). Draws ~3µA in backup — significant energy savings per fix.
//

// GPS UART (RAK3172 UART1 — PB6/PB7)
// Use Serial1 in Arduino framework, or the SparkFun library's serial mode.
// GPS TXD → R15 (33Ω series) → RAK3172 UART1_RX (PB7)
// GPS RXD ← R16 (33Ω series) ← RAK3172 UART1_TX (PB6)

#define GPS_SERIAL                  Serial1
#define GPS_BAUD                    9600

// GPS I2C (shared I2C bus — PA12/PA11, see I2C section)
#define GPS_I2C_ADDR                0x42

// GPS control pins
#define PIN_GPS_RESET_N             PA0   // Active-low reset, 10kΩ pullup (R18) to GPS VCC.

// GPS configuration constants
#define GPS_DYNMODEL_AIRBORNE_4G    8     // UBX-CFG-NAVSPG-DYNMODEL value
#define GPS_BACKUP_CURRENT_UA       3     // V_BCKP quiescent draw in µA
#define GPS_HOTSTART_TIME_S         5     // Typical hot-start TTFF
#define GPS_COLDSTART_TIME_S        30    // Typical cold-start TTFF

// NOTE: Avoid simultaneous GPS acquisition and LoRa transmission. LoRa TX at
// +22 dBm can temporarily desense the GPS front-end. Sequence them.

// =============================================================================
//    I2C BUS — Shared, single pair of 4.7kΩ pull-ups (R11, R12)
// =============================================================================

#define PIN_I2C_SDA                 PA11  // Directly on RAK3172 Pin 10
#define PIN_I2C_SCL                 PA12  // Directly on RAK3172 Pin 9

// I2C Device Addresses (active on the bus)
#define I2C_ADDR_GPS                0x42  // u-blox MAX-M10S (U3) — fixed
#define I2C_ADDR_ACCEL              0x18  // LIS2DH12TR (U7) — SDO/SA0 tied to GND
#define I2C_ADDR_TEMP               0x48  // TMP117NAIYBGR (U5) — ADD0 tied to GND
#define I2C_ADDR_UV                 0x53  // LTR-390UV-01 (U6) — fixed address
#define I2C_ADDR_BARO               0x77  // MS5611-01BA03 (U4) — CSB tied to +3.3V

// =============================================================================
//    ACCELEROMETER — LIS2DH12TR (U7)
// =============================================================================
//
// Burst detection via hardware freefall interrupt.
//
// Configure freefall detection → fires INT1 → wakes MCU from STOP2 →
// firmware switches to rapid descent beaconing (fast GPS fixes, high LoRa
// rate). Zero polling required during normal float.
//
// At 1 Hz low-power mode (2 µA), the accelerometer continuously logs 3-axis
// data. Cross-correlating with MS5611 pressure oscillations characterizes
// atmospheric gravity waves — a measurement the atmospheric science community
// wants from balloon-borne platforms. Pendulum motion from the payload string
// dominates at ~1-3s period; gravity waves are 5-30 min period, so they're
// easily separable with a low-pass filter.

#define PIN_ACCEL_INT1              PA8   // LIS2DH12 INT1 output.
                                          // Configure as EXTI wakeup source for
                                          // freefall → burst detection.
                                          // Rising edge = interrupt active.

#define ACCEL_FREEFALL_THRESHOLD    0x16  // Suggested starting point (~350 mg)
#define ACCEL_FREEFALL_DURATION     0x03  // ~30 ms at ODR=100 Hz — tune empirically
#define ACCEL_LOWPOWER_ODR_HZ       1    // 1 Hz = 2 µA for gravity wave logging

// =============================================================================
//    TEMPERATURE — TMP117NAIYBGR (U5)
// =============================================================================
//
// One-shot mode: trigger a conversion, read the result, sensor returns to
// shutdown automatically. 0.25 µA shutdown current.

#define TMP117_ONESHOT_CONVERSION_MS  16  // Round up from 15.5 ms

// =============================================================================
//    BAROMETER — MS5611-01BA03 (U4)
// =============================================================================
//
// Has internal temperature reading alongside pressure (used for compensation).
// This is a secondary/redundant temp channel to cross-check against TMP117.
//
// OSR 4096 gives best resolution (~0.012 mbar) but takes ~9.04 ms per
// conversion. OSR 256 is faster (~0.6 ms) but noisier.

// =============================================================================
//    UV / AMBIENT LIGHT — LTR-390UV-01 (U6)
// =============================================================================
//
// Two modes: UV measurement and ambient light sensing (ALS).
// Poll on the same schedule as other sensors. No interrupt routed.
//
// Useful for: UV index, day/night detection, and crude ozone column
// estimation when combined with solar zenith angle from GPS time/position.

// =============================================================================
//    MICROPHONE — T3902 (MK1)
// =============================================================================
//
// Clocked via SPI1 in receive-only master mode at ~2.4 MHz. DMA captures
// the PDM bitstream; firmware decimates PDM→PCM in software (ST's PDM2PCM
// library or equivalent CIC filter).
//
// SPI1 alternate function mapping (AF5):
//   PB3 = SPI1_SCK  → drives mic CLK (through 33Ω series resistor)
//   PB4 = SPI1_MISO → receives mic PDM DATA (direct connection)
// This allows hardware SPI in receive-only master mode — no bit-banging needed.
//
// Power modes:
//   - Active: clock running, ~0.6 mA
//   - Sleep:  stop the clock = 12 µA (mic enters standby)
//   - Off:    remove VDD via power gating = 0 µA
// Wake-up from sleep: 32,768 SCK clock cycles (~13.6 ms at 2.4 MHz).

#define PIN_MIC_PDM_CLK             PB3   // SPI1_SCK (AF5). Clock output to T3902.
                                          // 33Ω series resistor between MCU and mic.

#define PIN_MIC_PDM_DATA            PB4   // SPI1_MISO (AF5). PDM data input from T3902.
                                          // Direct connection, no series resistor.

#define MIC_PDM_CLOCK_HZ            2400000  // ~2.4 MHz nominal
#define MIC_WAKEUP_CLOCKS           32768    // SCK cycles to wake from sleep

// T3902 SELECT pin is tied to GND → L channel selected.

// =============================================================================
//    POWER MANAGEMENT — BQ25570 (U1)
// =============================================================================
//
// Solar cells → VIN_DC → boost charger → VSTOR (supercap) → buck → VOUT (3.3V)

// --- VBAT_OK: power-good flag from BQ25570 ---
#define PIN_VBAT_OK                 PB5   // Digital input. Active high.
                                          // Connected through R8 (100kΩ series) to
                                          // BQ25570 VBAT_OK output (U1 pin 13).
                                          // HIGH = supercap above ~3.51V (rising)
                                          // LOW  = supercap below ~1.69V (falling)
                                          // Binary flag — no voltage granularity.
                                          // For real state-of-charge, read VSTOR ADC.

// --- VSTOR ADC: supercap voltage monitoring ---
//
// 1MΩ/1MΩ divider (R22 top, R23 bottom) → quiescent drain ~2.6 µA.
// V_ADC = VSTOR × (R23 / (R22 + R23)) = VSTOR × 0.5
// To recover VSTOR: multiply ADC reading by 2.
//
// CRITICAL: 500 kΩ Thévenin source impedance. The STM32 ADC needs at
// least 50 ms settling time after GPIO wakeup before sampling. Set the
// GPIO to analog mode, wait, then read. Do NOT rely on default sampling
// time — it's far too short for this impedance.

#define PIN_VSTOR_ADC               PA10  // ADC channel 4 (ADC_IN4)
#define VSTOR_DIVIDER_RATIO         2.0f  // Multiply ADC voltage by this
#define VSTOR_DIVIDER_R_TOP         1000000  // R22, 1MΩ
#define VSTOR_DIVIDER_R_BOT         1000000  // R23, 1MΩ
#define VSTOR_ADC_SETTLE_MS         50    // Minimum settling time

// --- Solar ADC: solar cell voltage monitoring ---
//
// 1MΩ/1MΩ divider (R19 top, R21 bottom) on +SOLAR rail.
// V_ADC = V_SOLAR × 0.5
// To recover V_SOLAR: multiply ADC reading by 2.
//
// Zero drain at night: when solar voltage is 0V, the divider draws nothing.
// Only drains during daylight. Firmware can use this for day/night detection
// and solar irradiance estimation.
//
// Same high source impedance as VSTOR — same 50 ms settling requirement.

#define PIN_SOLAR_ADC               PA15  // ADC channel 5 (ADC_IN5)
#define SOLAR_DIVIDER_RATIO         2.0f  // Multiply ADC voltage by this
#define SOLAR_DIVIDER_R_TOP         1000000  // R19, 1MΩ
#define SOLAR_DIVIDER_R_BOT         1000000  // R21, 1MΩ
#define SOLAR_ADC_SETTLE_MS         50    // Minimum settling time

// --- Programmed voltage thresholds (from resistor dividers R1-R8) ---
// These are hardware-set by resistors and cannot be changed in firmware.
#define BQ25570_VOUT_NOMINAL_MV     3312  // Buck output (VOUT_SET divider)
#define BQ25570_VBAT_OV_MV          5363  // Overvoltage lockout (supercap max)
#define BQ25570_VBAT_OK_RISE_MV     3510  // VBAT_OK asserts (rising)
#define BQ25570_VBAT_OK_FALL_MV     1692  // VBAT_OK deasserts (falling)

// --- VOUT_EN: buck converter enable (directly connected to VSTOR) ---
//

// --- Energy budget constants ---
//
// Supercap: 1F, VSTOR max ~5.36V, VSTOR min ~2.51V
// Available energy: 0.5 × 1F × (5.36² - 2.51²) ≈ 11.2 J
//
// Sleep baseline: ~7.5 µA total system → ~1.3 J over 12 hours
// GPS hot-start + LoRa TX: ~0.3 J per cycle (varies with fix time)
//
// Night survival: dropping GPS at night and running baro + LoRa beacons
// every 30 min uses ~1.6 J total over 12 hours — easily survivable.
// GPS hot-starts every 30 min at night exceeds the budget.
// GPS every 2 hours at night is tight but possible.

#define SUPERCAP_CAPACITANCE_F      1.0f
#define SUPERCAP_MAX_V              5.36f  // VBAT_OV - margin
#define SUPERCAP_MIN_V              2.51f  // Below VBAT_OK_FALL
#define SUPERCAP_ENERGY_J           11.2f  // 0.5 × C × (Vmax² - Vmin²)
#define SYSTEM_SLEEP_CURRENT_UA     7.5f   // Total system in STOP2

// --- Graduated power shedding thresholds (suggested, tune empirically) ---
// Firmware should implement tiered load shedding based on VSTOR ADC reading.
#define POWER_TIER_FULL_V           4.5f  // Full operations (GPS + all sensors + LoRa)
#define POWER_TIER_REDUCED_V        3.5f  // Reduced beacon rate, fewer sensors
#define POWER_TIER_NO_GPS_V         3.0f  // Drop GPS, baro + LoRa only
#define POWER_TIER_EMERGENCY_V      2.8f  // Emergency — LoRa distress beacon only

// =============================================================================
// 9. LoRa / LoRaWAN — RAK3172 integrated SX1262
// =============================================================================
//
// Two separate antennas on the board:
//   - AE1: LoRa antenna
//   - AE2: GPS antenna
// Different frequencies (868/915 MHz vs 1575.42 MHz), no sharing possible.
// No harmonic interference between them.

// #define PB12  /* FORBIDDEN — internal LoRa band select. DO NOT USE. */

// ---- Antenna cut lengths (λ/4 monopole) ----
//   GPS L1 1575.42 MHz  →  48 mm
//   LoRa 915 MHz        →  82 mm   (US915/AU915/KR920/AS923)
//   LoRa 868 MHz        →  86 mm   (EU868/RU864/IN865)
//   LoRa Multi-region   →  83 mm   (wideband compromise 868-928 MHz)
//   Wire length MUST match the configured frequency region.
//
//   TX power: +14 dBm ≈ 44 mA, +20 dBm ≈ 87 mA. Never exceed +22 dBm.
//   NEVER transmit without antenna soldered — reflects into PA, kills FE.
//   GPS cold fix with wire monopole: 40-60s (budget ON time accordingly).
//   GPS warm/hot fix: 1-10s (requires backup RAM powered).
//   50 Ω impedance on both RF paths. No matching network needed.

// ESD protection: D1, D3 (PESD5V0U1BB, 0.5pF) on both antennas.

// =============================================================================
// 10. SPARE GPIOs — Available on J3 header
// =============================================================================

#define PIN_SPARE_PA1               PA1   // Spare GPIO
#define PIN_SPARE_PA9               PA9   // Spare GPIO
#define PIN_SPARE_PB2               PB2   // Spare GPIO

// =============================================================================
// 11. SWD DEBUG INTERFACE
// =============================================================================

#define PIN_SWDIO                   PA13  // SWD data — directly on RAK3172 Pin 7
#define PIN_SWCLK                   PA14  // SWD clock — directly on RAK3172 Pin 8

// =============================================================================
// 12. BOARD METADATA
// =============================================================================

#define BOARD_NAME                  "Stratolink PICO Mainboard"
#define BOARD_REVISION              "2026-02-27"
#define BOARD_AUTHORS               "Teddy Warner, Shepherd Kruse, Caleb Kruse"
#define BOARD_THICKNESS_MM          0.4f
#define BOARD_LAYERS                2
#define BOARD_WEIGHT_TARGET_G       15    // Total system weight limit

#endif // BOARD_H
