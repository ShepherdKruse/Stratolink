#ifndef CRYPTO_AES128_H
#define CRYPTO_AES128_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/* Small allocation-free AES-128/CMAC primitive shared by LoRaWAN and B2B. */
#define AES128_CMAC_MAX_BYTES 271u

void aes128_encrypt_block(const uint8_t key[16], const uint8_t input[16],
                          uint8_t output[16]);
bool aes128_cmac(const uint8_t key[16], const uint8_t* message, size_t length,
                 uint8_t mac[16]);

#endif
