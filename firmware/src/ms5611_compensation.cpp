#include "ms5611_compensation.h"

bool ms5611_compensate(const uint16_t coefficients[6],
                       uint32_t d1,
                       uint32_t d2,
                       ms5611_compensated_t* out) {
    if (!coefficients || !out ||
        d1 == 0 || d1 > 0xFFFFFFu ||
        d2 == 0 || d2 > 0xFFFFFFu) {
        return false;
    }

    const uint16_t any = coefficients[0] | coefficients[1] |
                         coefficients[2] | coefficients[3] |
                         coefficients[4] | coefficients[5];
    const uint16_t all = coefficients[0] & coefficients[1] &
                         coefficients[2] & coefficients[3] &
                         coefficients[4] & coefficients[5];
    if (any == 0 || all == 0xFFFFu) return false;

    const int64_t dt = (int64_t)d2 - ((int64_t)coefficients[4] << 8);
    int64_t temperature =
        2000 + ((dt * (int64_t)coefficients[5]) >> 23);
    int64_t offset =
        ((int64_t)coefficients[1] << 16) +
        (((int64_t)coefficients[3] * dt) >> 7);
    int64_t sensitivity =
        ((int64_t)coefficients[0] << 15) +
        (((int64_t)coefficients[2] * dt) >> 8);

    if (temperature < 2000) {
        const int64_t below_20 = temperature - 2000;
        const int64_t t2 = (dt * dt) >> 31;
        int64_t offset2 = (5 * below_20 * below_20) >> 1;
        int64_t sensitivity2 = offset2 >> 1;

        if (temperature < -1500) {
            const int64_t below_minus_15 = temperature + 1500;
            const int64_t cold2 = below_minus_15 * below_minus_15;
            offset2 += 7 * cold2;
            sensitivity2 += (11 * cold2) >> 1;
        }

        temperature -= t2;
        offset -= offset2;
        sensitivity -= sensitivity2;
    }

    const int64_t pressure =
        ((((int64_t)d1 * sensitivity) >> 21) - offset) >> 15;

    ms5611_compensated_t result = {};
    result.temperature_centi_c =
        temperature > INT32_MAX ? INT32_MAX :
        temperature < INT32_MIN ? INT32_MIN :
        (int32_t)temperature;
    result.pressure_centi_hpa =
        pressure <= 0 ? 0 :
        pressure > INT32_MAX ? INT32_MAX :
        (int32_t)pressure;
    *out = result;
    return true;
}
