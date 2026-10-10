#ifndef TMP117_CONVERSION_H
#define TMP117_CONVERSION_H

#include <stdint.h>

/*
 * TI TMP117 datasheet SBOS740C specifies 7.8125 mC/LSB, or exactly
 * 128 counts/C. Convert to the flight telemetry unit of decidegrees C:
 *
 *   raw * 10 / 128 == raw * 5 / 64
 *
 * Both primary telemetry wire versions and every ground decoder use 0.1 C/LSB. Returning
 * centidegrees here would make a healthy 25.0 C TMP117 serialize as 250.0 C
 * while the MS5611 fallback serialized the same temperature correctly.
 * Round to the nearest decidegree, symmetrically around zero.
 * The reset value 0x8000 represents -256 C until the first conversion and is
 * outside the device's rated operating range, so it must not be reported as
 * a physical measurement.
 *
 * https://www.ti.com/lit/ds/symlink/tmp117.pdf
 */
static inline bool tmp117_raw_to_decidegrees(int16_t raw,
                                             int16_t* temperature_dc) {
    if (!temperature_dc || raw == INT16_MIN) return false;
    int32_t scaled = (int32_t)raw * 5;
    scaled += scaled >= 0 ? 32 : -32;
    *temperature_dc = (int16_t)(scaled / 64);
    return true;
}

#endif /* TMP117_CONVERSION_H */
