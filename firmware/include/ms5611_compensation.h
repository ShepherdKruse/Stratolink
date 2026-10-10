#ifndef MS5611_COMPENSATION_H
#define MS5611_COMPENSATION_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    int32_t temperature_centi_c;
    int32_t pressure_centi_hpa;
} ms5611_compensated_t;

/**
 * Apply the MS5611-01BA03 first- and second-order compensation equations.
 *
 * coefficients contains C1..C6 in datasheet order. D1 and D2 are the raw
 * 24-bit pressure and temperature conversions. The result uses the native
 * datasheet units: 0.01 degrees C and 0.01 hPa.
 *
 * Returns false for null pointers, missing/saturated calibration, or invalid
 * ADC words. The output is committed only on success.
 */
bool ms5611_compensate(const uint16_t coefficients[6],
                       uint32_t d1,
                       uint32_t d2,
                       ms5611_compensated_t* out);

#endif /* MS5611_COMPENSATION_H */
