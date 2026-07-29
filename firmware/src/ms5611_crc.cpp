#include "ms5611_crc.h"

bool ms5611_prom_crc_valid(const uint16_t prom[8]) {
    if (!prom) return false;

    uint16_t words[8];
    for (uint8_t i = 0; i < 8; ++i) words[i] = prom[i];

    const uint8_t expected = (uint8_t)(words[7] & 0x000Fu);
    words[7] &= 0xFF00u;

    uint16_t remainder = 0;
    for (uint8_t byte_index = 0; byte_index < 16; ++byte_index) {
        const uint16_t word = words[byte_index >> 1];
        remainder ^= (byte_index & 1u)
            ? (uint16_t)(word & 0x00FFu)
            : (uint16_t)(word >> 8);

        for (uint8_t bit = 0; bit < 8; ++bit) {
            remainder = (remainder & 0x8000u)
                ? (uint16_t)((remainder << 1) ^ 0x3000u)
                : (uint16_t)(remainder << 1);
        }
    }

    return (uint8_t)((remainder >> 12) & 0x0Fu) == expected;
}
