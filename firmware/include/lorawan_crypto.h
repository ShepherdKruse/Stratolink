#ifndef LORAWAN_CRYPTO_H
#define LORAWAN_CRYPTO_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/* Pure LoRaWAN 1.0.x cryptographic framing. These helpers contain no radio or
 * Arduino dependencies, so the exact production paths can be host-vector
 * tested independently from the STM32 build. */
bool lorawan_crypto_cmac4(const uint8_t key[16], const uint8_t* message,
                          size_t length, uint8_t mac[4]);
bool lorawan_crypto_payload(const uint8_t key[16], uint32_t dev_addr,
                            uint32_t frame_counter, uint8_t direction,
                            uint8_t* payload, size_t length);
bool lorawan_crypto_mic(const uint8_t key[16], uint32_t dev_addr,
                        uint32_t frame_counter, uint8_t direction,
                        const uint8_t* message, size_t length,
                        uint8_t mac[4]);
bool lorawan_crypto_join_accept(const uint8_t key[16],
                                const uint8_t* encrypted, size_t length,
                                uint8_t* plaintext);
bool lorawan_crypto_session_key(const uint8_t key[16], uint8_t key_type,
                                const uint8_t join_nonce[3],
                                const uint8_t net_id[3], uint16_t dev_nonce,
                                uint8_t session_key[16]);

#endif
