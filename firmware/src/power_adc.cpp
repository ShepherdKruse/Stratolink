#include "power_adc.h"
#include "stratolink_pins.h"
#include "config.h"
#include <Arduino.h>
#include "stm32wlxx_hal.h"

/* STM32WL VREFINT factory-calibrated raw value, measured at VDDA = 3.3 V.
 * VREFINT_CAL_ADDR comes from stm32wlxx_ll_adc.h (0x1FFF75AA).
 * Using it lets us compute the actual runtime VDDA:
 *   VDDA_mv = 3300 * VREFINT_CAL / VREFINT_raw
 * Without this we'd assume VDDA = 3.3 V — wrong by however much the
 * buck output actually differs, including when VSTOR is in dropout. */
#define VREFINT_CAL_VREF_MV VREFINT_CAL_VREF

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

/* Read VREFINT and infer runtime VDDA in millivolts. Returns 0 if VREFINT
 * could not be read. Refresh before each VSTOR conversion: below buck
 * regulation VDD follows VSTOR, and a ratiometric divider read cannot detect
 * that fall unless its reference voltage is measured at the same time.
 *
 * A missing or implausible reference must fail CLOSED. Substituting nominal
 * 3.3 V in dropout can overestimate VSTOR and authorize GPS/TX on a rail that
 * cannot fund the load. Returning 0 makes the current load gate skip and the
 * next independent ADC read retry automatically. */
static uint16_t s_vdda_mv = 0;
static uint16_t s_vrefint_raw = 0;
static uint16_t s_vstor_raw = 0;
static uint16_t s_solar_raw = 0;
static uint16_t adc_read_raw(uint32_t channel);
static void refresh_vdda_mv(void) {
    uint16_t cal = *VREFINT_CAL_ADDR;
    uint32_t raw = adc_read_raw(ADC_CHANNEL_VREFINT);
    s_vrefint_raw = (uint16_t)raw;
    /* Validate in 32-bit space before narrowing. Otherwise a corrupt tiny raw
     * sample can compute above 65.535 V, wrap through uint16_t, and alias into
     * the apparently valid 1.8-3.6 V load-authorization window. */
    s_vdda_mv = power_adc_vdda_from_vrefint(
        cal, (uint16_t)raw, (uint32_t)VREFINT_CAL_VREF_MV);
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
    /* Calibration is part of the safety boundary, not optional trimming. An
     * uncalibrated but plausible high reading could authorize a load on a
     * marginal rail, so leave adc_initialized false on any HAL failure. */
    if (HAL_ADCEx_Calibration_Start(&s_hadc) != HAL_OK) return;

    /* Enable the VREFINT internal-channel path so reading
     * ADC_CHANNEL_VREFINT actually returns the reference voltage.
     * On STM32WL ADC_CCR lives on the common-config struct ADC1_COMMON. */
    SET_BIT(ADC_COMMON->CCR, ADC_CCR_VREFEN);

    adc_initialized = true;

    /* One-shot VREFINT read to learn actual VDDA — must happen after the
     * calibration above and before any user channel reads. */
    refresh_vdda_mv();
}

bool power_adc_quiesce(void) {
    /* RM0461 requires ADVREGEN=0 before Stop mode to keep consumption low.
     * HAL_ADC_Stop() clears ADEN but deliberately leaves both the ADC's
     * internal regulator and the VREFINT path enabled, so stopping each
     * conversion is not sufficient for the multi-minute flight idle.
     *
     * Keep the clock live until every control bit has been read back. A
     * peripheral reset is the bounded fallback if the normal HAL shutdown is
     * rejected by a stale/busy ADC state. The caller resets the MCU rather
     * than entering a long STOP1 if even that readback fails. */
    __HAL_RCC_ADC_CLK_ENABLE();
    if (s_hadc.Instance != ADC) {
        s_hadc = {};
        s_hadc.Instance = ADC;
    }

    (void)HAL_ADC_Stop(&s_hadc);
    CLEAR_BIT(ADC_COMMON->CCR, ADC_CCR_VREFEN);
    (void)HAL_ADCEx_DisableVoltageRegulator(&s_hadc);

    constexpr uint32_t adc_on_mask = ADC_CR_ADEN | ADC_CR_ADVREGEN;
    bool quiesced = ((ADC->CR & adc_on_mask) == 0u) &&
                     ((ADC_COMMON->CCR & ADC_CCR_VREFEN) == 0u);
    if (!quiesced) {
        __HAL_RCC_ADC_FORCE_RESET();
        __HAL_RCC_ADC_RELEASE_RESET();
        quiesced = ((ADC->CR & adc_on_mask) == 0u) &&
                    ((ADC_COMMON->CCR & ADC_CCR_VREFEN) == 0u);
    }

    /* The APB2 sleep-enable bit resets enabled on STM32WL. Clear it as well
     * as the run clock so the same quiescence contract holds in the bounded
     * shallow-WFI fallback, not only in deep STOP1. */
    __HAL_RCC_ADC_CLK_SLEEP_DISABLE();
    __HAL_RCC_ADC_CLK_DISABLE();
    s_hadc = {};
    adc_initialized = false;
    s_vdda_mv = 0;
    s_vrefint_raw = 0;
    s_vstor_raw = 0;
    s_solar_raw = 0;
    return quiesced;
}

static uint16_t adc_read_raw(uint32_t channel) {
    ADC_ChannelConfTypeDef sConfig = {};
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

static uint16_t read_mv(uint32_t channel, float divider_ratio,
                        uint16_t* raw_out) {
    if (channel == ADC_CHANNEL_6) refresh_vdda_mv();
    uint32_t raw = adc_read_raw(channel);
    if (raw_out) *raw_out = (uint16_t)raw;
    uint32_t vdda_mv = power_adc_validated_vdda_mv(s_vdda_mv);
    if (vdda_mv == 0) return 0;
    uint32_t mv = (raw * vdda_mv) / 4096u;
    return (uint16_t)((float)mv * divider_ratio);
}

uint16_t power_adc_read_vSTOR_mv(void) {
    if (!adc_initialized) power_adc_init();
    if (!adc_initialized) return 0;
    return read_mv(ADC_CHANNEL_6, VSTOR_DIVIDER_RATIO, &s_vstor_raw); /* PA10 */
}

uint16_t power_adc_read_solar_mv(void) {
    if (!adc_initialized) power_adc_init();
    if (!adc_initialized) return 0;
    return read_mv(ADC_CHANNEL_11, SOLAR_DIVIDER_RATIO, &s_solar_raw); /* PA15 */
}

uint16_t power_adc_debug_vdda_mv(void) { return s_vdda_mv; }
uint16_t power_adc_debug_vrefint_raw(void) { return s_vrefint_raw; }
uint16_t power_adc_debug_vstor_raw(void) { return s_vstor_raw; }
uint16_t power_adc_debug_solar_raw(void) { return s_solar_raw; }

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
