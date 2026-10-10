#ifndef DEVNONCE_STORE_H
#define DEVNONCE_STORE_H

#include <stdbool.h>
#include <stdint.h>

/**
 * Allocate and persist the next OTAA DevNonce before it is transmitted.
 *
 * Two reserved flash pages form a power-loss-safe append-only journal. The
 * value never repeats or wraps; false means storage/programming failed or all
 * 65536 values have been exhausted, in which case joining must fail closed.
 */
bool devnonce_next(uint16_t* out);

/* Pure helpers exposed for host corruption/exhaustion tests. */
uint64_t devnonce_record_encode(uint16_t nonce);
bool devnonce_record_decode(uint64_t record, uint16_t* nonce);
bool devnonce_value_next(bool have_previous, uint16_t previous, uint16_t* next);

#endif
