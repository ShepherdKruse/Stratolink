#include "lorawan_crypto.h"

#include "crypto_aes128.h"

#include <string.h>

bool lorawan_crypto_cmac4(const uint8_t key[16], const uint8_t* message,
                          size_t length, uint8_t mac[4]) {
    if (!key || !mac || (length && !message)) return false;
    uint8_t full[16];
    if (!aes128_cmac(key, message, length, full)) return false;
    memcpy(mac, full, 4);
    return true;
}

bool lorawan_crypto_payload(const uint8_t key[16], uint32_t dev_addr,
                            uint32_t frame_counter, uint8_t direction,
                            uint8_t* payload, size_t length) {
    if (!key || (length && !payload) || direction > 1u ||
        length > 255u * 16u) return false;
    size_t blocks = (length + 15u) / 16u;
    for (size_t block = 0; block < blocks; ++block) {
        uint8_t a[16] = {0x01, 0, 0, 0, 0, direction};
        a[6] = (uint8_t)dev_addr;
        a[7] = (uint8_t)(dev_addr >> 8);
        a[8] = (uint8_t)(dev_addr >> 16);
        a[9] = (uint8_t)(dev_addr >> 24);
        a[10] = (uint8_t)frame_counter;
        a[11] = (uint8_t)(frame_counter >> 8);
        a[12] = (uint8_t)(frame_counter >> 16);
        a[13] = (uint8_t)(frame_counter >> 24);
        a[15] = (uint8_t)(block + 1u);
        uint8_t stream[16];
        aes128_encrypt_block(key, a, stream);
        size_t offset = block * 16u;
        size_t count = length - offset;
        if (count > 16u) count = 16u;
        for (size_t i = 0; i < count; ++i) {
            payload[offset + i] ^= stream[i];
        }
    }
    return true;
}

bool lorawan_crypto_mic(const uint8_t key[16], uint32_t dev_addr,
                        uint32_t frame_counter, uint8_t direction,
                        const uint8_t* message, size_t length,
                        uint8_t mac[4]) {
    if (!key || !mac || (length && !message) || direction > 1u ||
        length > 255u) return false;
    uint8_t framed[16 + 255];
    uint8_t* b0 = framed;
    memset(b0, 0, 16);
    b0[0] = 0x49;
    b0[5] = direction;
    b0[6] = (uint8_t)dev_addr;
    b0[7] = (uint8_t)(dev_addr >> 8);
    b0[8] = (uint8_t)(dev_addr >> 16);
    b0[9] = (uint8_t)(dev_addr >> 24);
    b0[10] = (uint8_t)frame_counter;
    b0[11] = (uint8_t)(frame_counter >> 8);
    b0[12] = (uint8_t)(frame_counter >> 16);
    b0[13] = (uint8_t)(frame_counter >> 24);
    b0[15] = (uint8_t)length;
    if (length) memcpy(framed + 16, message, length);
    return lorawan_crypto_cmac4(key, framed, 16u + length, mac);
}

bool lorawan_crypto_join_accept(const uint8_t key[16],
                                const uint8_t* encrypted, size_t length,
                                uint8_t* plaintext) {
    if (!key || !encrypted || !plaintext || length == 0 ||
        length > 32u || (length % 16u) != 0) return false;
    for (size_t offset = 0; offset < length; offset += 16u) {
        aes128_encrypt_block(key, encrypted + offset, plaintext + offset);
    }
    return true;
}

bool lorawan_crypto_session_key(const uint8_t key[16], uint8_t key_type,
                                const uint8_t join_nonce[3],
                                const uint8_t net_id[3], uint16_t dev_nonce,
                                uint8_t session_key[16]) {
    if (!key || !join_nonce || !net_id || !session_key ||
        (key_type != 1u && key_type != 2u)) return false;
    uint8_t block[16] = {};
    block[0] = key_type;
    memcpy(block + 1, join_nonce, 3);
    memcpy(block + 4, net_id, 3);
    block[7] = (uint8_t)dev_nonce;
    block[8] = (uint8_t)(dev_nonce >> 8);
    aes128_encrypt_block(key, block, session_key);
    return true;
}
