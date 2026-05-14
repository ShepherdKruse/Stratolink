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

/**
 * Put the SX1262 SubGHz radio into SLEEP retention mode (~3 µA, config kept).
 * MUST be called before MCU STOP2 entry — otherwise the radio sits in
 * STDBY_RC drawing ~600 µA, which both wrecks the night-survival energy
 * budget and (on the RAK3172 module) appears to leave pending interrupts
 * that hard-reset the chip when STOP2 attempts to enter or exit.
 *
 * Subsequent transmit() calls wake the radio implicitly via SetStandby.
 */
void lorawan_sleep(void);

#endif /* LORAWAN_H */
