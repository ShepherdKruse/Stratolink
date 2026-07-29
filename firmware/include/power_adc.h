#ifndef POWER_ADC_H
#define POWER_ADC_H

#include <stdint.h>
#include <stdbool.h>

/** Power tier for load shedding (from board.h thresholds). */
typedef enum {
    POWER_TIER_FULL = 0,     /* VSTOR >= 4.5 V: GPS + all sensors + LoRa */
    POWER_TIER_REDUCED,      /* >= 3.5 V: reduced beacon rate */
    POWER_TIER_NO_GPS,       /* >= 3.0 V: baro + LoRa only */
    POWER_TIER_EMERGENCY,    /* >= 2.8 V: load-shed; RF paths require >= 3.0 V */
    POWER_TIER_CRITICAL      /* < 2.8 V: may not TX reliably */
} power_tier_t;

/**
 * Validate the runtime VDDA estimate used to scale the high-impedance divider.
 * Zero is the deliberate fail-closed sentinel: a nominal-voltage fallback can
 * overestimate VSTOR while the buck is in dropout and wrongly authorize load.
 */
static inline uint16_t power_adc_validated_vdda_mv(uint16_t measured_mv) {
    return (measured_mv >= 1800u && measured_mv <= 3600u) ? measured_mv : 0u;
}

/**
 * Convert factory-calibration and live VREFINT ADC samples to VDDA without
 * narrowing before the safety-range check. A corrupt very-small raw sample
 * can produce hundreds of volts arithmetically; truncating that result to
 * uint16_t first can alias it into the otherwise-valid 1.8-3.6 V window.
 */
static inline uint16_t power_adc_vdda_from_vrefint(uint16_t calibration_raw,
                                                   uint16_t measured_raw,
                                                   uint32_t calibration_mv) {
    if (calibration_raw == 0u || calibration_raw == UINT16_MAX ||
        measured_raw == 0u || calibration_mv == 0u) {
        return 0u;
    }
    uint32_t measured_mv =
        (calibration_mv * (uint32_t)calibration_raw) / measured_raw;
    if (measured_mv < 1800u || measured_mv > 3600u) return 0u;
    return (uint16_t)measured_mv;
}

/**
 * Initialize ADC and pins for VSTOR (PA10) and Solar (PA15).
 * Call once from setup().
 */
void power_adc_init(void);

/**
 * Disable the ADC, its VREFINT path, internal voltage regulator, and bus
 * clock before MCU STOP1. Returns true only when ADEN, ADVREGEN, and VREFEN
 * all read back clear. The next measurement reinitializes and recalibrates.
 */
bool power_adc_quiesce(void);

/**
 * Read supercap voltage (VSTOR) in millivolts. The ADC uses a 642 us sample
 * window so the board's 500 kohm divider source settles to 12-bit accuracy.
 * Returns 0 (load gates fail closed) if the runtime VDDA reference is invalid.
 */
uint16_t power_adc_read_vSTOR_mv(void);

/**
 * Read solar voltage in millivolts.
 * Uses the same 642 us high-impedance-divider sampling window as VSTOR.
 * Returns 0 if no valid runtime VDDA reference is available.
 */
uint16_t power_adc_read_solar_mv(void);

/** Bench diagnostics for validating ADC scaling; not used for tier policy. */
uint16_t power_adc_debug_vdda_mv(void);
uint16_t power_adc_debug_vrefint_raw(void);
uint16_t power_adc_debug_vstor_raw(void);
uint16_t power_adc_debug_solar_raw(void);

/**
 * Get current power tier from VSTOR (does one VSTOR read with settle).
 */
power_tier_t power_adc_get_tier(void);

/**
 * Return true if we have enough energy for full ops (GPS + LoRa).
 */
bool power_adc_can_use_gps(void);

/**
 * Return the broad tier-level TX eligibility result. Every actual RF path
 * independently re-reads and requires at least 3.0 V at the load boundary;
 * this preliminary predicate alone never authorizes a transmission.
 */
bool power_adc_can_tx(void);

/**
 * Return true if we should read I2C sensors (baro, temp, accel).
 * False for EMERGENCY/CRITICAL to save current (LoRa beacon only).
 */
bool power_adc_should_read_sensors(void);

/**
 * Return recommended sleep interval in seconds for the given tier.
 * Per-tier value = the matching SLEEP_INTERVAL_*_SEC macro in config.h
 * (CRITICAL shares EMERGENCY; see power_adc.cpp for the switch).
 */
uint32_t power_adc_get_sleep_interval_sec(power_tier_t tier);

#endif /* POWER_ADC_H */
