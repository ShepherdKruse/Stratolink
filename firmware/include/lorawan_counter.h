#ifndef LORAWAN_COUNTER_H
#define LORAWAN_COUNTER_H

#include <stdint.h>
#include <stdbool.h>

/**
 * Reconstruct a full FCntDown from the 16-bit value carried on air.
 *
 * next_expected is the first counter not yet consumed by the device. Zero is
 * also the fresh-session sentinel, so the first authenticated downlink accepts
 * its complete 16-bit value. Later calls accept only a forward distance below
 * 2^15, handle the 16-bit rollover, and reject 32-bit exhaustion.
 */
bool lorawan_fcntdown_reconstruct(uint32_t next_expected,
                                 uint16_t on_air_low,
                                 uint32_t* accepted_counter);

#endif
