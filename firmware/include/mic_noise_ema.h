#ifndef MIC_NOISE_EMA_H
#define MIC_NOISE_EMA_H

#include <stdint.h>

/*
 * Update an unsigned noise-power estimate without relying on mixed
 * signed/unsigned addition or implementation-defined right shift of a
 * negative value. Division is defined to truncate toward zero; the result
 * therefore always stays between the old floor and the sample. A floor of
 * one prevents the detector threshold from collapsing to zero.
 */
static inline uint32_t mic_noise_ema_update(uint32_t floor_sq,
                                            uint32_t sample_sq,
                                            uint8_t shift) {
    if (shift > 31u) shift = 31u;
    const int64_t difference =
        (int64_t)sample_sq - (int64_t)floor_sq;
    const int64_t divisor = (int64_t)(1ULL << shift);
    const int64_t updated =
        (int64_t)floor_sq + difference / divisor;
    return updated < 1 ? 1u : (uint32_t)updated;
}

#endif /* MIC_NOISE_EMA_H */
