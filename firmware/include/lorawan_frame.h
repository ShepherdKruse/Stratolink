#ifndef LORAWAN_FRAME_H
#define LORAWAN_FRAME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Pure authenticated LoRaWAN 1.0.x receive-frame decoding. Keeping this
 * independent from RadioLib lets the exact gate that decides whether RX1 may
 * suppress RX2 run under host sanitizers. */

enum {
    LORAWAN_FRAME_REJECT_NONE = 0,
    LORAWAN_FRAME_REJECT_LENGTH = 1,
    LORAWAN_FRAME_REJECT_MHDR = 2,
    LORAWAN_FRAME_REJECT_DEVADDR = 3,
    LORAWAN_FRAME_REJECT_COUNTER = 4,
    LORAWAN_FRAME_REJECT_HEADER = 5,
    LORAWAN_FRAME_REJECT_MIC = 6,
};

typedef struct {
    uint32_t frame_counter;
    uint8_t fport;
    uint8_t len;
    uint8_t data[64];
} lorawan_decoded_downlink_t;

/**
 * Authenticate and decrypt an unconfirmed data-down frame. `next_counter` is
 * the first acceptable FCntDown. On failure `out` is left zeroed and `reject`
 * identifies the fail-closed reason.
 */
bool lorawan_frame_decode_downlink(
    const uint8_t nwk_s_key[16], const uint8_t app_s_key[16],
    uint32_t dev_addr, uint32_t next_counter,
    const uint8_t* frame, size_t frame_len,
    lorawan_decoded_downlink_t* out, uint8_t* reject);

/**
 * Authenticate and decrypt a 17- or 33-byte join-accept. The MHDR remains
 * clear on air; the encrypted body is decoded into `plaintext` only when its
 * AppKey MIC is valid. This is the gate used before RX1 can suppress RX2.
 */
bool lorawan_frame_decode_join_accept(
    const uint8_t app_key[16], const uint8_t* frame, size_t frame_len,
    uint8_t plaintext[33]);

#endif
