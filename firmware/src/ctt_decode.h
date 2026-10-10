#ifndef CTT_DECODE_H
#define CTT_DECODE_H

/* Decode logic for CTT (Cellular Tracking Technologies) wildlife tag beacons:
 * LifeTag / PowerTag / HybridTag, the 434 MHz FSK tags used by the Motus
 * network on birds, bats, and large insects.
 *
 * On-air frame (2-FSK, 25 kbps, +-25 kHz dev, no shaping):
 *   preamble 0xAA x3 | sync 0xD3 0x91 | id[4] | crc8
 * The 4 id bytes each come from a 32-entry DC-balanced symbol dictionary
 * (5 data bits per byte -> 20-bit Motus id space inside a 32-bit raw id).
 * CRC-8 poly 0x07 init 0x00 over the 4 id bytes.
 *
 * Sources: rtl_433 ctt_life_power_hybrid.c (merged May 2026) and the
 * RadioLib-based CTT test-tag firmware (github.com/tve/motus-test-tags).
 * Pure logic, no radio dependencies, host-testable. */

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    uint32_t id_raw;      /* 4 id bytes big-endian, as rtl_433 reports */
    uint32_t id_motus;    /* 20-bit dictionary-index id (5 bits/byte) */
    bool     crc_ok;      /* crc8 over id bytes matched */
    bool     motus_valid; /* all 4 bytes are dictionary members */
} ctt_frame_t;

/* Decode a 5-byte payload (4 id + crc).  Returns true when crc_ok. */
bool ctt_decode(const uint8_t payload[5], ctt_frame_t* out);

#endif
