#ifndef CTT_TEST_TAG_H
#define CTT_TEST_TAG_H

#include <stddef.h>
#include <stdint.h>

/* Diagnostic-only helpers for producing the reverse-engineered CTT/Motus
 * five-byte test-tag frame. Nothing in the flight source includes this file.
 * The encoding is pinned to tve/motus-test-tags commit
 * 26e0b8aaea4890c936f1df9070a4fc263a03c8af. */

static inline uint8_t ctt_test_tag_crc8(const uint8_t* data, size_t length) {
    uint8_t crc = 0;
    if (!data) return crc;
    while (length--) {
        crc ^= *data++;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (uint8_t)((crc & 0x80u) ? (crc << 1) ^ 0x07u : crc << 1);
        }
    }
    return crc;
}

static inline bool ctt_test_tag_encode(uint32_t motus_id, uint8_t out[5]) {
    static const uint8_t dictionary[32] = {
        0x00, 0x07, 0x19, 0x1E, 0x2A, 0x2D, 0x33, 0x34,
        0x4B, 0x4C, 0x52, 0x55, 0x61, 0x66, 0x78, 0x7F,
        0x80, 0x87, 0x99, 0x9E, 0xAA, 0xAD, 0xB3, 0xB4,
        0xCB, 0xCC, 0xD2, 0xD5, 0xE1, 0xE6, 0xF8, 0xFF,
    };
    if (!out || motus_id > 0xFFFFFu) return false;

    /* Least-significant five-bit group is the first on-air ID byte. */
    for (uint8_t i = 0; i < 4; ++i) {
        out[i] = dictionary[motus_id & 0x1Fu];
        motus_id >>= 5;
    }
    out[4] = ctt_test_tag_crc8(out, 4);
    return true;
}

#endif
