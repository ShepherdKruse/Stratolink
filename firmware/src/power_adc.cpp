#include "power_adc.h"
#include "stratolink_pins.h"
#include "config.h"
#include <Arduino.h>
#include "stm32wlxx_hal.h"

#ifndef ADC_VREF_MV
#define ADC_VREF_MV 3300
#endif

/* Direct HAL ADC: bypasses STM32duino analogRead defaults that don't tolerate
 * the 1 MΩ + 1 MΩ dividers on VSTOR (R22/R23) and +SOLAR (R19/R21).
 *
 * Source impedance ≈ 500 kΩ, internal sample cap ≈ 5 pF → τ = 2.5 µs.
 * Default analogRead at 4 MHz ADC clock × 19.5 cycles ≈ 5 µs (2τ) settles
 * to ~13 % of source — useless for a tier comparator.
 *
 * Fix: ADC_CLOCK_ASYNC_DIV64 → 250 kHz ADC clock × 160.5 cycles ≈ 642 µs (256τ).
 * Settles to <1 ppm — well past 12-bit accuracy. Each read costs ~700 µs;
 * we read once per main loop, so the cost is invisible in the energy budget. */

static bool adc_initialized = false;
static ADC_HandleTypeDef s_hadc;

void power_adc_init(void) {
    pinMode(PIN_VSTOR_ADC, INPUT_ANALOG);
    pinMode(PIN_SOLAR_ADC, INPUT_ANALOG);

    __HAL_RCC_ADC_CLK_ENABLE();

    s_hadc.Instance                   = ADC;
    s_hadc.Init.ClockPrescaler        = ADC_CLOCK_ASYNC_DIV64;
    s_hadc.Init.Resolution            = ADC_RESOLUTION_12B;
    s_hadc.Init.DataAlign             = ADC_DATAALIGN_RIGHT;
    s_hadc.Init.ScanConvMode          = ADC_SCAN_DISABLE;
    s_hadc.Init.EOCSelection          = ADC_EOC_SINGLE_CONV;
    s_hadc.Init.LowPowerAutoWait      = DISABLE;
    s_hadc.Init.LowPowerAutoPowerOff  = DISABLE;
    s_hadc.Init.ContinuousConvMode    = DISABLE;
    s_hadc.Init.NbrOfConversion       = 1;
    s_hadc.Init.DiscontinuousConvMode = DISABLE;
    s_hadc.Init.ExternalTrigConv      = ADC_SOFTWARE_START;
    s_hadc.Init.ExternalTrigConvEdge  = ADC_EXTERNALTRIGCONVEDGE_NONE;
    s_hadc.Init.DMAContinuousRequests = DISABLE;
    s_hadc.Init.Overrun               = ADC_OVR_DATA_PRESERVED;
    s_hadc.Init.SamplingTimeCommon1   = ADC_SAMPLETIME_160CYCLES_5;
    s_hadc.Init.SamplingTimeCommon2   = ADC_SAMPLETIME_160CYCLES_5;
    s_hadc.Init.OversamplingMode      = DISABLE;
    s_hadc.Init.TriggerFrequencyMode  = ADC_TRIGGER_FREQ_LOW;

    if (HAL_ADC_Init(&s_hadc) != HAL_OK) return;
    HAL_ADCEx_Calibration_Start(&s_hadc);

    adc_initialized = true;
}

static uint16_t adc_read_raw(uint32_t channel) {
    ADC_ChannelConfTypeDef sConfig = {0};
    sConfig.Channel      = channel;
    sConfig.Rank         = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLINGTIME_COMMON_1;
    if (HAL_ADC_ConfigChannel(&s_hadc, &sConfig) != HAL_OK) return 0;

    if (HAL_ADC_Start(&s_hadc) != HAL_OK) return 0;
    if (HAL_ADC_PollForConversion(&s_hadc, 50) != HAL_OK) {
        HAL_ADC_Stop(&s_hadc);
        return 0;
    }
    uint16_t raw = (uint16_t)HAL_ADC_GetValue(&s_hadc);
    HAL_ADC_Stop(&s_hadc);
    return raw;
}

static uint16_t read_mv(uint32_t channel, float divider_ratio) {
    uint32_t raw = adc_read_raw(channel);
    uint32_t mv  = (raw * (uint32_t)ADC_VREF_MV) / 4096u;
    return (uint16_t)((float)mv * divider_ratio);
}

uint16_t power_adc_read_vSTOR_mv(void) {
    if (!adc_initialized) power_adc_init();
    return read_mv(ADC_CHANNEL_6, VSTOR_DIVIDER_RATIO);   /* PA10 */
}

uint16_t power_adc_read_solar_mv(void) {
    if (!adc_initialized) power_adc_init();
    return read_mv(ADC_CHANNEL_11, SOLAR_DIVIDER_RATIO);  /* PA15 */
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
    return power_adc_get_tier() <= POWER_TIER_EMERGENCY;
}

bool power_adc_should_read_sensors(void) {
    return power_adc_get_tier() <= POWER_TIER_NO_GPS;
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
