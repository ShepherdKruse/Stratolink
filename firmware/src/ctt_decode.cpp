#include "ctt_decode.h"

/* The 32-entry Motus symbol dictionary (rtl_433 ctt_life_power_hybrid.c).
 * Each on-air id byte must be one of these; its index is 5 bits of the
 * 20-bit Motus id. */
static const uint8_t motus_code[32] = {
    0x00, 0x07, 0x19, 0x1E, 0x2A, 0x2D, 0x33, 0x34,
    0x4B, 0x4C, 0x52, 0x55, 0x61, 0x66, 0x78, 0x7F,
    0x80, 0x87, 0x99, 0x9E, 0xAA, 0xAD, 0xB3, 0xB4,
    0xCB, 0xCC, 0xD2, 0xD5, 0xE1, 0xE6, 0xF8, 0xFF};

static int8_t motus_index(uint8_t b) {
    for (uint8_t i = 0; i < 32; i++)
        if (motus_code[i] == b) return (int8_t)i;
    return -1;
}

/* CRC-8, poly 0x07, init 0x00 (SMBus), MSB-first, over the 4 id bytes. */
static uint8_t ctt_crc8(const uint8_t* d, uint8_t n) {
    uint8_t crc = 0x00;
    while (n--) {
        crc ^= *d++;
        for (uint8_t i = 0; i < 8; i++)
            crc = (uint8_t)((crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1));
    }
    return crc;
}

bool ctt_decode(const uint8_t payload[5], ctt_frame_t* out) {
    if (!payload || !out) return false;

    out->id_raw = ((uint32_t)payload[0] << 24) | ((uint32_t)payload[1] << 16) |
                  ((uint32_t)payload[2] << 8)  |  (uint32_t)payload[3];
    out->crc_ok = (ctt_crc8(payload, 4) == payload[4]);

    int8_t i0 = motus_index(payload[0]);
    int8_t i1 = motus_index(payload[1]);
    int8_t i2 = motus_index(payload[2]);
    int8_t i3 = motus_index(payload[3]);
    out->motus_valid = (i0 >= 0 && i1 >= 0 && i2 >= 0 && i3 >= 0);
    out->id_motus = out->motus_valid
        ? (((uint32_t)i0 << 15) | ((uint32_t)i1 << 10) | ((uint32_t)i2 << 5) | (uint32_t)i3)
        : 0;

    return out->crc_ok;
}
