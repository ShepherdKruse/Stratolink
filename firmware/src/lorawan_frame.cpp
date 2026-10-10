#include "lorawan_frame.h"

#include "lorawan_counter.h"
#include "lorawan_crypto.h"

#include <string.h>

static void set_reject(uint8_t* reject, uint8_t value) {
    if (reject) *reject = value;
}

bool lorawan_frame_decode_downlink(
    const uint8_t nwk_s_key[16], const uint8_t app_s_key[16],
    uint32_t dev_addr, uint32_t next_counter,
    const uint8_t* frame, size_t frame_len,
    lorawan_decoded_downlink_t* out, uint8_t* reject) {
    if (out) memset(out, 0, sizeof(*out));
    set_reject(reject, LORAWAN_FRAME_REJECT_LENGTH);
    if (!nwk_s_key || !app_s_key || !frame || !out || frame_len < 12u ||
        frame_len > 64u) return false;

    /* This compact stack implements LoRaWAN 1.0.x unconfirmed data-down only:
     * MType=011, RFU=000, Major=00. An authenticated but unsupported MHDR must
     * not be misinterpreted as the implemented frame shape. */
    if (frame[0] != 0x60u) {
        set_reject(reject, LORAWAN_FRAME_REJECT_MHDR);
        return false;
    }
    uint32_t received_addr = (uint32_t)frame[1] |
        ((uint32_t)frame[2] << 8) | ((uint32_t)frame[3] << 16) |
        ((uint32_t)frame[4] << 24);
    if (received_addr != dev_addr) {
        set_reject(reject, LORAWAN_FRAME_REJECT_DEVADDR);
        return false;
    }

    uint16_t low_counter =
        (uint16_t)((uint16_t)frame[6] | ((uint16_t)frame[7] << 8));
    uint32_t full_counter = 0;
    if (!lorawan_fcntdown_reconstruct(
            next_counter, low_counter, &full_counter)) {
        set_reject(reject, LORAWAN_FRAME_REJECT_COUNTER);
        return false;
    }

    size_t header_len = 8u + (frame[5] & 0x0Fu);
    if (frame_len < header_len + 4u) {
        set_reject(reject, LORAWAN_FRAME_REJECT_HEADER);
        return false;
    }

    uint8_t mic[4];
    if (!lorawan_crypto_mic(nwk_s_key, dev_addr, full_counter, 1,
                            frame, frame_len - 4u, mic) ||
        memcmp(mic, frame + frame_len - 4u, sizeof(mic)) != 0) {
        set_reject(reject, LORAWAN_FRAME_REJECT_MIC);
        return false;
    }

    out->frame_counter = full_counter;
    if (frame_len > header_len + 4u) {
        out->fport = frame[header_len];
        size_t payload_len = frame_len - header_len - 1u - 4u;
        if (payload_len > sizeof(out->data)) {
            memset(out, 0, sizeof(*out));
            set_reject(reject, LORAWAN_FRAME_REJECT_LENGTH);
            return false;
        }
        out->len = (uint8_t)payload_len;
        memcpy(out->data, frame + header_len + 1u, payload_len);
        const uint8_t* key = out->fport == 0 ? nwk_s_key : app_s_key;
        if (!lorawan_crypto_payload(key, dev_addr, full_counter, 1,
                                    out->data, payload_len)) {
            memset(out, 0, sizeof(*out));
            set_reject(reject, LORAWAN_FRAME_REJECT_MIC);
            return false;
        }
    }
    set_reject(reject, LORAWAN_FRAME_REJECT_NONE);
    return true;
}

bool lorawan_frame_decode_join_accept(
    const uint8_t app_key[16], const uint8_t* frame, size_t frame_len,
    uint8_t plaintext[33]) {
    if (plaintext) memset(plaintext, 0, 33u);
    if (!app_key || !frame || !plaintext ||
        (frame_len != 17u && frame_len != 33u) ||
        frame[0] != 0x20u) return false;

    plaintext[0] = frame[0];
    if (!lorawan_crypto_join_accept(
            app_key, frame + 1u, frame_len - 1u, plaintext + 1u)) {
        memset(plaintext, 0, 33u);
        return false;
    }
    uint8_t mic[4];
    if (!lorawan_crypto_cmac4(app_key, plaintext, frame_len - 4u, mic) ||
        memcmp(mic, plaintext + frame_len - 4u, sizeof(mic)) != 0) {
        memset(plaintext, 0, 33u);
        return false;
    }
    return true;
}
