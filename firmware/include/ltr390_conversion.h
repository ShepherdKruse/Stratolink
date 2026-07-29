#ifndef LTR390_CONVERSION_H
#define LTR390_CONVERSION_H

#include <stdint.h>

/*
 * Lite-On LTR-390UV-01 datasheet Rev. 1.7 specifies 1400 counts/UVI at
 * gain 18x and 20-bit/400 ms. Counts scale with integration time, so the
 * flight setting (gain 18x, 18-bit/100 ms) uses 1400 / 4 = 350 counts/UVI.
 *
 * https://optoelectronics.liteon.com/upload/download/DS86-2015-0004/
 * LTR-390UV-01_Final_%20DS_V1.7.PDF
 */
#define LTR390_UV_COUNTS_PER_UVI_18X_18BIT 350u

static inline uint8_t ltr390_uv_index_from_raw(uint32_t raw) {
    uint32_t uvi = raw / LTR390_UV_COUNTS_PER_UVI_18X_18BIT;
    /* 0xFE is the telemetry unavailable sentinel. Skip it and preserve 0xFF
     * as a real high/saturated reading. */
    return (uvi >= UINT8_MAX - 1u) ? UINT8_MAX : (uint8_t)uvi;
}

/*
 * Datasheet ALS formula at gain 1x, 18-bit/100 ms, and no optical window:
 * lux = 0.6 * raw / (gain * integration factor) = 0.6 * raw.
 */
static inline uint16_t ltr390_lux_from_raw_1x_18bit(uint32_t raw) {
    /* 0xFFFE is the telemetry unavailable sentinel. Raw 109224 would produce
     * that exact code, so promote it and higher values to the genuine 0xFFFF
     * saturation code. Clamp before multiplying so corrupt input cannot wrap. */
    if (raw >= 109224u) return UINT16_MAX;
    return (uint16_t)((raw * 6u) / 10u);
}

#endif /* LTR390_CONVERSION_H */
