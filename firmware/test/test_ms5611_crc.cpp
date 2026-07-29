#include <cstdint>
#include <cstdio>

#include "ms5611_crc.h"

static int failures = 0;

#define CHECK(expr) do {                                                     \
    if (!(expr)) {                                                           \
        std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); \
        ++failures;                                                          \
    }                                                                        \
} while (0)

int main() {
    /* MS5611 datasheet example coefficients. The reserved words and CRC
     * nibble below are selected so the complete image has CRC4 == 0. */
    const uint16_t valid[8] = {
        0x0000, 40127, 36924, 23317, 23282, 33464, 28312, 0x0000
    };
    CHECK(ms5611_prom_crc_valid(valid));

    uint16_t corrupted[8];
    for (int i = 0; i < 8; ++i) corrupted[i] = valid[i];
    corrupted[3] ^= 0x0040u;
    CHECK(!ms5611_prom_crc_valid(corrupted));

    for (int i = 0; i < 8; ++i) corrupted[i] = valid[i];
    corrupted[7] ^= 0x0001u;
    CHECK(!ms5611_prom_crc_valid(corrupted));

    CHECK(!ms5611_prom_crc_valid(nullptr));

    if (failures) return 1;
    std::puts("MS5611 CRC4 tests passed");
    return 0;
}
