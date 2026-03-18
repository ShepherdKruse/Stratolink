#ifndef LORAWAN_H
#define LORAWAN_H

#include <stdint.h>
#include <stdbool.h>

/** Maximum uplink payload size (LoRaWAN allows up to 222 at SF7; we use 38). */
#define LORAWAN_PAYLOAD_MAX 64

/**
 * Initialize LoRaWAN stack (region from config, keys from secrets).
 * Call once from setup(). Returns true on success.
 */
bool lorawan_init(void);

/**
 * Perform OTAA join. Blocking until joined or timeout_ms.
 */
bool lorawan_join(uint32_t timeout_ms);

/**
 * Send unconfirmed uplink. payload_len must be <= LORAWAN_PAYLOAD_MAX.
 * Returns true if send was queued/successful.
 */
bool lorawan_send_uplink(const uint8_t* payload, uint8_t payload_len);

/**
 * Return true if we are joined and can send.
 */
bool lorawan_joined(void);

#endif /* LORAWAN_H */
