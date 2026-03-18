#ifndef POWER_ADC_H
#define POWER_ADC_H

#include <stdint.h>
#include <stdbool.h>

/** Power tier for load shedding (from board.h thresholds). */
typedef enum {
    POWER_TIER_FULL = 0,     /* VSTOR >= 4.5 V: GPS + all sensors + LoRa */
    POWER_TIER_REDUCED,      /* >= 3.5 V: reduced beacon rate */
    POWER_TIER_NO_GPS,       /* >= 3.0 V: baro + LoRa only */
    POWER_TIER_EMERGENCY,    /* >= 2.8 V: LoRa distress only */
    POWER_TIER_CRITICAL      /* < 2.8 V: may not TX reliably */
} power_tier_t;

/**
 * Initialize ADC and pins for VSTOR (PA10) and Solar (PA15).
 * Call once from setup().
 */
void power_adc_init(void);

/**
 * Read supercap voltage (VSTOR) in millivolts.
 * Ensures 50 ms settling after switching to analog before sampling.
 */
uint16_t power_adc_read_vSTOR_mv(void);

/**
 * Read solar voltage in millivolts.
 * Same 50 ms settling requirement.
 */
uint16_t power_adc_read_solar_mv(void);

/**
 * Get current power tier from VSTOR (does one VSTOR read with settle).
 */
power_tier_t power_adc_get_tier(void);

/**
 * Return true if we have enough energy for full ops (GPS + LoRa).
 */
bool power_adc_can_use_gps(void);

/**
 * Return true if we have enough energy to attempt LoRa TX.
 */
bool power_adc_can_tx(void);

/**
 * Return true if we should read I2C sensors (baro, temp, accel).
 * False for EMERGENCY/CRITICAL to save current (LoRa beacon only).
 */
bool power_adc_should_read_sensors(void);

/**
 * Return recommended sleep interval in seconds for the given tier (Phase 3).
 * FULL=60, REDUCED=120, NO_GPS=300, EMERGENCY=120, CRITICAL=120.
 */
uint32_t power_adc_get_sleep_interval_sec(power_tier_t tier);

#endif /* POWER_ADC_H */
