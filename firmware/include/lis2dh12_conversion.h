#ifndef LIS2DH12_CONVERSION_H
#define LIS2DH12_CONVERSION_H

#include <stdbool.h>
#include <stdint.h>

/*
 * ST LIS2DH12 low-power mode at +/-2 g is 8-bit with 16 mg/digit.
 * 16 mg * 9.80665 m/s^2/g = 15.69064 cm/s^2 per digit. The telemetry
 * representation is integral cm/s^2, so use 15.69 without floating point.
 */
static inline int16_t lis2dh12_low_power_to_cm_s2(int8_t raw) {
    return (int16_t)(((int32_t)raw * 1569) / 100);
}

/* INT1_SRC.IA (bit 6) is the aggregate interrupt decision after the configured
 * AOI/6D logic. The XL/YL/ZL status bits can be set individually at rest and
 * must not be mistaken for a completed all-axis freefall condition. */
static inline bool lis2dh12_int1_active(uint8_t source) {
    return (source & 0x40u) != 0u;
}

/* Clearing a recovery state requires positive evidence. An unavailable I2C
 * sample is not evidence that drag/landing restored acceleration; the bounded
 * burst cap contains a persistent sensor fault. */
static inline bool lis2dh12_freefall_is_cleared(bool sample_ok,
                                                bool magnitude_cleared) {
    return sample_ok && magnitude_cleared;
}

#endif /* LIS2DH12_CONVERSION_H */
