#include "power_adc.h"
#include "stratolink_pins.h"
#include "config.h"
#include <Arduino.h>
#include "stm32wlxx_hal.h"

#ifndef ADC_VREF_MV_NOMINAL
#define ADC_VREF_MV_NOMINAL 3300
#endif

/* STM32WL VREFINT factory-calibrated raw value, measured at VDDA = 3.0 V.
 * VREFINT_CAL_ADDR comes from stm32wlxx_ll_adc.h (0x1FFF75AA).
 * Using it lets us compute the actual runtime VDDA:
 *   VDDA_mv = 3000 * VREFINT_CAL / VREFINT_raw
 * Without this we'd assume VDDA = 3.3 V — wrong by however much the
 * buck output actually differs, including when VSTOR is in dropout. */
#define VREFINT_CAL_VREF_MV 3000

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

/* Read VREFINT once after init and infer the runtime VDDA in millivolts.
 * Cached because VDDA only changes when the buck regulator's input
 * (VSTOR) crosses the dropout point — slowly enough that we don't need
 * to refresh every cycle.  Returns 0 if VREFINT couldn't be read, which
 * the caller treats as "use the nominal 3300 mV fallback". */
static uint16_t s_vdda_mv = 0;
static uint16_t adc_read_raw(uint32_t channel);
static void refresh_vdda_mv(void) {
    uint16_t cal = *VREFINT_CAL_ADDR;
    if (cal == 0 || cal == 0xFFFF) { s_vdda_mv = 0; return; }
    uint32_t raw = adc_read_raw(ADC_CHANNEL_VREFINT);
    if (raw == 0) { s_vdda_mv = 0; return; }
    s_vdda_mv = (uint16_t)(((uint32_t)VREFINT_CAL_VREF_MV * cal) / raw);
}

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

    /* Enable the VREFINT internal-channel path so reading
     * ADC_CHANNEL_VREFINT actually returns the reference voltage.
     * On STM32WL ADC_CCR lives on the common-config struct ADC1_COMMON. */
    SET_BIT(ADC_COMMON->CCR, ADC_CCR_VREFEN);

    adc_initialized = true;

    /* One-shot VREFINT read to learn actual VDDA — must happen after the
     * calibration above and before any user channel reads. */
    refresh_vdda_mv();
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
    /* Bench check (2026-05) showed the VREFINT-derived VDDA over-corrected:
     * applying it shifted vstor from 3380 mV → 5935 mV when the multimeter
     * read 4700 mV.  Mechanism is likely the same ADC scaling error that
     * makes the divider read low; VREFINT reads low too and the math turns
     * that into a falsely-high VDDA, double-correcting.  Keeping the read
     * for future debug telemetry (see s_vdda_mv) but using the nominal
     * 3300 mV for the actual conversion. */
    (void)s_vdda_mv;
    uint32_t mv = (raw * (uint32_t)ADC_VREF_MV_NOMINAL) / 4096u;
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
