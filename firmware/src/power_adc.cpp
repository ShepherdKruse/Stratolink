#include "power_adc.h"
#include "stratolink_pins.h"
#include "config.h"
#include <Arduino.h>

#ifndef ADC_RESOLUTION
#define ADC_RESOLUTION 4096
#endif
#ifndef ADC_VREF_MV
#define ADC_VREF_MV 3300
#endif

static bool adc_initialized = false;

void power_adc_init(void) {
    pinMode(PIN_VSTOR_ADC, INPUT_ANALOG);
    pinMode(PIN_SOLAR_ADC, INPUT_ANALOG);
    adc_initialized = true;
}

static uint16_t read_adc_mv(uint32_t pin, float divider_ratio) {
    delay(VSTOR_ADC_SETTLE_MS);
    uint32_t raw = analogRead(pin);
    uint32_t mv = (raw * (uint32_t)ADC_VREF_MV) / ADC_RESOLUTION;
    return (uint16_t)((float)mv * divider_ratio);
}

uint16_t power_adc_read_vSTOR_mv(void) {
    if (!adc_initialized) power_adc_init();
    return read_adc_mv(PIN_VSTOR_ADC, VSTOR_DIVIDER_RATIO);
}

uint16_t power_adc_read_solar_mv(void) {
    if (!adc_initialized) power_adc_init();
    return read_adc_mv(PIN_SOLAR_ADC, SOLAR_DIVIDER_RATIO);
}

power_tier_t power_adc_get_tier(void) {
    uint16_t v = power_adc_read_vSTOR_mv();
    float vf = (float)v / 1000.0f;
    if (vf >= POWER_TIER_FULL_V)       return POWER_TIER_FULL;
    if (vf >= POWER_TIER_REDUCED_V)    return POWER_TIER_REDUCED;
    if (vf >= POWER_TIER_NO_GPS_V)     return POWER_TIER_NO_GPS;
    if (vf >= POWER_TIER_EMERGENCY_V)  return POWER_TIER_EMERGENCY;
    return POWER_TIER_CRITICAL;
}

bool power_adc_can_use_gps(void) {
    return power_adc_get_tier() <= POWER_TIER_REDUCED;
}

bool power_adc_can_tx(void) {
    return true; /* Always allow TX — even CRITICAL tier sends distress beacons */
}

bool power_adc_should_read_sensors(void) {
    return true; /* TEMP: bench PSU on 3.3V, no supercap — revert when supercaps arrive */
}

uint32_t power_adc_get_sleep_interval_sec(power_tier_t tier) {
#ifndef SLEEP_INTERVAL_FULL_SEC
#define SLEEP_INTERVAL_FULL_SEC      TRANSMIT_INTERVAL_SEC
#define SLEEP_INTERVAL_REDUCED_SEC   (TRANSMIT_INTERVAL_SEC * 2)
#define SLEEP_INTERVAL_NO_GPS_SEC    (TRANSMIT_INTERVAL_SEC * 5)
#define SLEEP_INTERVAL_EMERGENCY_SEC (TRANSMIT_INTERVAL_SEC * 2)
#endif
    switch (tier) {
        case POWER_TIER_FULL:      return SLEEP_INTERVAL_FULL_SEC;
        case POWER_TIER_REDUCED:   return SLEEP_INTERVAL_REDUCED_SEC;
        case POWER_TIER_NO_GPS:    return SLEEP_INTERVAL_NO_GPS_SEC;
        case POWER_TIER_EMERGENCY:
        case POWER_TIER_CRITICAL:  return SLEEP_INTERVAL_EMERGENCY_SEC;
        default:                   return TRANSMIT_INTERVAL_SEC;
    }
}
