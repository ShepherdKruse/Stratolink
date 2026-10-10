#include <cstdint>
#include <cstdio>

#include "ms5611_compensation.h"

static int failures = 0;

#define CHECK(expr) do {                                                     \
    if (!(expr)) {                                                           \
        std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); \
        ++failures;                                                          \
    }                                                                        \
} while (0)

int main() {
    const uint16_t coefficients[6] = {
        40127, 36924, 23317, 23282, 33464, 28312
    };
    ms5611_compensated_t result = {};

    /* MS5611-01BA03 datasheet calculation example. */
    CHECK(ms5611_compensate(coefficients, 9085466, 8569150, &result));
    CHECK(result.temperature_centi_c == 2007);
    CHECK(result.pressure_centi_hpa == 100009);

    /* Below -15 C both second-order branches must apply. These exact integer
     * vectors exercise the stratospheric path that was absent in early
     * firmware; omitting the extra cold correction changes pressure by
     * hundreds of hPa at the coldest point. */
    CHECK(ms5611_compensate(coefficients, 9085466, 7500000, &result));
    CHECK(result.temperature_centi_c == -2130);
    CHECK(result.pressure_centi_hpa == 91910);
    CHECK(ms5611_compensate(coefficients, 9085466, 6500000, &result));
    CHECK(result.temperature_centi_c == -6965);
    CHECK(result.pressure_centi_hpa == 76043);

    const ms5611_compensated_t sentinel = {123, 456};
    result = sentinel;
    CHECK(!ms5611_compensate(nullptr, 9085466, 8569150, &result));
    CHECK(result.temperature_centi_c == sentinel.temperature_centi_c);
    CHECK(result.pressure_centi_hpa == sentinel.pressure_centi_hpa);
    CHECK(!ms5611_compensate(coefficients, 0, 8569150, &result));
    CHECK(!ms5611_compensate(coefficients, 9085466, 0x1000000u, &result));
    const uint16_t empty[6] = {};
    CHECK(!ms5611_compensate(empty, 9085466, 8569150, &result));
    const uint16_t saturated[6] = {
        0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu
    };
    CHECK(!ms5611_compensate(saturated, 9085466, 8569150, &result));
    CHECK(!ms5611_compensate(coefficients, 9085466, 8569150, nullptr));

    if (failures) return 1;
    std::puts("MS5611 datasheet and stratospheric compensation vectors passed");
    return 0;
}
